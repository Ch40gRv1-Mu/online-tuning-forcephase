#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

struct PropagationState {
 std::vector<int> counts,xors;
 std::vector<unsigned char> sat;
 std::vector<signed char> assigned;
 bool conflict=false;
 int assigned_count=0;
};

struct PropagationFormula {
 int nv=-1,nc=-1,active_count=0;
 long long literals=0,empty_clauses=0;
 std::vector<std::vector<int>> clauses,occ;
 std::vector<unsigned char> taut,active;
 static size_t idx(int lit){return 2*size_t(std::abs(lit))+(lit<0);}
 explicit PropagationFormula(const std::string &path) {
  std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("open input failed");
  std::string text((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
  const char *p=text.data(),*end=p+text.size();std::vector<int> c;
  while(p<end) {
   if(*p==' '||*p=='\t'||*p=='\n'||*p=='\r'){++p;continue;}
   if(*p=='c'){while(p<end&&*p!='\n')++p;continue;}
   if(*p=='p'){
    const char *a=p;while(p<end&&*p!='\n')++p;
    std::istringstream h(std::string(a,p));std::string tag,fmt,extra;
    if(nv>=0||!(h>>tag>>fmt>>nv>>nc)||fmt!="cnf"||nv<0||nc<0||(h>>extra))throw std::runtime_error("invalid header");
    clauses.reserve(nc);continue;
   }
   bool neg=false;if(*p=='-'){neg=true;++p;}else if(*p=='+')++p;
   if(p==end||*p<'0'||*p>'9')throw std::runtime_error("invalid token");
   long long lit=0;while(p<end&&*p>='0'&&*p<='9'){lit=lit*10+(*p-'0');++p;if(lit>2147483647LL)throw std::runtime_error("literal overflow");}
   if(lit){if(nv<0||lit>nv)throw std::runtime_error("literal out of bounds");c.push_back(neg?-(int)lit:(int)lit);}
   else{clauses.push_back(std::move(c));c.clear();}
  }
  if(nv<0||!c.empty()||(int)clauses.size()!=nc)throw std::runtime_error("incomplete input");
  occ.resize(2*(size_t(nv)+1));active.resize(nv+1,0);taut.resize(nc,0);
  std::vector<int> seen(2*(size_t(nv)+1),-1);
  for(int ci=0;ci<nc;++ci){
   auto &raw=clauses[ci];empty_clauses+=raw.empty();literals+=raw.size();std::vector<int> unique;
   for(int lit:raw){active[std::abs(lit)]=1;if(seen[idx(-lit)]==ci)taut[ci]=1;if(seen[idx(lit)]!=ci){unique.push_back(lit);seen[idx(lit)]=ci;}}
   if(taut[ci])raw.clear();else{raw=std::move(unique);for(int lit:raw)occ[idx(lit)].push_back(ci);}
  }
  for(int v=1;v<=nv;++v)active_count+=active[v]!=0;
 }
 PropagationState propagate(PropagationState s,std::vector<int> queue) const {
  if(s.conflict)return s;
  for(size_t head=0;head<queue.size()&&!s.conflict;++head){
   int lit=queue[head],v=std::abs(lit),value=lit>0?1:-1;
   if(s.assigned[v]){if(s.assigned[v]!=value)s.conflict=true;continue;}
   s.assigned[v]=value;++s.assigned_count;
   for(int ci:occ[idx(lit)])s.sat[ci]=1;
   for(int ci:occ[idx(-lit)]){
    if(s.sat[ci])continue;
    --s.counts[ci];s.xors[ci]^=-lit;
    if(!s.counts[ci]){s.conflict=true;break;}
    if(s.counts[ci]==1)queue.push_back(s.xors[ci]);
   }
  }
  return s;
 }
 PropagationState root() const {
  PropagationState s;s.counts.resize(nc);s.xors.resize(nc,0);s.sat=taut;s.assigned.resize(nv+1,0);s.conflict=empty_clauses>0;
  std::vector<int> units;
  for(int ci=0;ci<nc;++ci){if(taut[ci])continue;auto &c=clauses[ci];s.counts[ci]=c.size();for(int lit:c)s.xors[ci]^=lit;if(c.size()==1)units.push_back(c[0]);}
  return propagate(std::move(s),std::move(units));
 }
 int remaining(const PropagationState &s) const {return std::count(s.sat.begin(),s.sat.end(),0);}
 std::vector<int> free_variables(const PropagationState &s) const {
  std::vector<unsigned char> seen(nv+1,0);std::vector<int> free;
  for(int ci=0;ci<nc;++ci)if(!s.sat[ci])for(int lit:clauses[ci])if(!s.assigned[std::abs(lit)])seen[std::abs(lit)]=1;
  for(int v=1;v<=nv;++v)if(seen[v])free.push_back(v);
  return free;
 }
};
