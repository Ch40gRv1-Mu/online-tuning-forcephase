#pragma once
// Shared TA100 public-CNF parser. No search, propagation, labels or names as features.
#include <algorithm>
#include <cmath>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace ta100 {
using Lit = int32_t;
using Clause = std::vector<Lit>;
inline double cpu_now() { return double(std::clock()) / CLOCKS_PER_SEC; }
struct Limits {
  uint64_t max_bytes=100000000, max_variables=5000000;
  uint64_t max_clauses=2000000, max_literals=20000000;
};
struct CNF {
  uint32_t n=0;
  uint64_t declared_clauses=0, raw_clauses=0, raw_literals=0, input_bytes=0;
  uint64_t repeated_literals=0, tautological_clauses=0, active_variables=0;
  // Sorted unique signed literals; original clause IDs retained, including tautologies.
  std::vector<Clause> clauses;
  std::vector<uint8_t> tautological;
  // Non-tautological clause occurrences, one per signed literal, IDs ascending.
  std::vector<std::vector<uint32_t>> pos, neg;
  double parse_cpu_s=0,shared_index_cpu_s=0;
};
inline CNF read_cnf(const std::string &path, const Limits &limits=Limits()) {
  const double started=cpu_now();
  CNF f;
  f.input_bytes=std::filesystem::file_size(path);
  if(f.input_bytes>limits.max_bytes) throw std::runtime_error("RESOURCE_LIMIT: input bytes");
  std::ifstream input(path);
  if(!input) throw std::runtime_error("FORMAT_ERROR: cannot open CNF");
  bool header=false; Clause pending; std::string line;
  while(std::getline(input,line)) {
    const char *p=line.c_str(); while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;
    if(!*p||*p=='c') continue;
    if(*p=='p') {
      if(header||!pending.empty())throw std::runtime_error("FORMAT_ERROR: duplicate header");
      std::istringstream h(p);std::string marker,kind;uint64_t n,m;
      if(!(h>>marker>>kind>>n>>m)||marker!="p"||kind!="cnf")throw std::runtime_error("FORMAT_ERROR: invalid header");
      if(n>limits.max_variables||m>limits.max_clauses)throw std::runtime_error("RESOURCE_LIMIT: header dimensions");
      f.n=uint32_t(n);f.declared_clauses=m;f.pos.resize(n+1);f.neg.resize(n+1);
      f.clauses.reserve(size_t(m));f.tautological.reserve(size_t(m));header=true;continue;
    }
    if(!header)throw std::runtime_error("FORMAT_ERROR: literals before header");
    while(*p) {
      while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;
      if(!*p)break;char *end=nullptr;const long value=std::strtol(p,&end,10);
      if(end==p||value>long(f.n)||value< -long(f.n))throw std::runtime_error("FORMAT_ERROR: bad literal");
      p=end;
      if(value) {
        if(++f.raw_literals>limits.max_literals)throw std::runtime_error("RESOURCE_LIMIT: literals");
        pending.push_back(Lit(value));continue;
      }
      if(f.raw_clauses>=f.declared_clauses)throw std::runtime_error("FORMAT_ERROR: extra clause");
      std::sort(pending.begin(),pending.end());
      const size_t before=pending.size();pending.erase(std::unique(pending.begin(),pending.end()),pending.end());
      f.repeated_literals+=before-pending.size();
      bool taut=false;
      for(Lit l:pending)if(l>0&&std::binary_search(pending.begin(),pending.end(),-l)){taut=true;break;}
      const uint32_t cid=uint32_t(f.raw_clauses++);
      f.tautological.push_back(taut);f.tautological_clauses+=taut;
      if(!taut)for(Lit l:pending)(l>0?f.pos[uint32_t(l)]:f.neg[uint32_t(-l)]).push_back(cid);
      f.clauses.push_back(std::move(pending));pending.clear();
    }
  }
  if(!header||!pending.empty()||f.raw_clauses!=f.declared_clauses)
    throw std::runtime_error("FORMAT_ERROR: missing header/terminator/clause count");
  for(uint32_t v=1;v<=f.n;++v)f.active_variables+=!f.pos[v].empty()||!f.neg[v].empty();
  f.parse_cpu_s=cpu_now()-started;return f;
}
inline const std::vector<uint32_t>& occurrences(const CNF&f,Lit l) {
  return l>0?f.pos[uint32_t(l)]:f.neg[uint32_t(-l)];
}
inline std::string escaped(const std::string&s) {
  std::string out;
  for(unsigned char c:s) {if(c=='"'||c=='\\')out+='\\';if(c>=32)out+=char(c);}
  return out;
}
struct Block {
  std::string key,status="COMPLETE",reason;
  double value=NAN,cpu_s=0;
  int64_t count=0;uint64_t denominator=0,work=0;
};
inline Block fraction(std::string key,int64_t count,uint64_t denominator,uint64_t work=0) {
  Block b;b.key=std::move(key);b.count=count;b.denominator=denominator;b.work=work;
  if(denominator)b.value=double(count)/denominator;
  else b.status="UNDEFINED",b.reason="zero eligible denominator";
  return b;
}
inline Block unavailable(std::string key,std::string status,std::string reason,uint64_t work=0) {
  Block b;b.key=std::move(key);b.status=std::move(status);b.reason=std::move(reason);b.work=work;return b;
}
inline void emit(const CNF&f,const std::vector<Block>&blocks,const std::string&group) {
  std::cout<<std::setprecision(15)<<"{\"schema\":\"ta100.static.v1\",\"group\":\""<<escaped(group)<<"\",\"features\":{";
  bool first=true;
  for(const auto&b:blocks){if(!first)std::cout<<',';first=false;std::cout<<'"'<<escaped(b.key)<<"\":";
    if(b.status=="COMPLETE"&&std::isfinite(b.value))std::cout<<b.value;else std::cout<<"null";}
  std::cout<<"},\"blocks\":{";first=true;
  for(const auto&b:blocks){if(!first)std::cout<<',';first=false;
    std::cout<<'"'<<escaped(b.key)<<"\":{\"status\":\""<<escaped(b.status)<<"\",\"reason\":\""<<escaped(b.reason)
      <<"\",\"count\":"<<b.count<<",\"denominator\":"<<b.denominator<<",\"work\":"<<b.work<<",\"cpu_s\":"<<b.cpu_s<<'}';}
  std::cout<<"},\"metadata\":{\"header_variables\":"<<f.n<<",\"header_clauses\":"<<f.declared_clauses
    <<",\"raw_clauses\":"<<f.raw_clauses<<",\"raw_literals\":"<<f.raw_literals<<",\"input_bytes\":"<<f.input_bytes
    <<",\"parse_cpu_s\":"<<f.parse_cpu_s<<",\"shared_index_cpu_s\":"<<f.shared_index_cpu_s<<"}}\n";std::cout.flush();
}
} // namespace ta100
