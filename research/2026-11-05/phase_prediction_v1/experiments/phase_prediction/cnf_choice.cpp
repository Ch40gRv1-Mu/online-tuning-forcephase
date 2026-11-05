// Complete signed exactly-one blocks from raw CNF, no solver or identities.
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>
using U=uint32_t;
static uint64_t key(U a,U b){if(a>b)std::swap(a,b);return (uint64_t(a)<<32)|b;}
int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("usage: cnf_choice INPUT.cnf");
    auto start=std::chrono::steady_clock::now();std::ifstream input(argv[1]);
    if(!input)throw std::runtime_error("cannot open input");
    U variables=0;uint64_t expected=0,clauses=0,active=0,length=0;bool header=false,exact=true;
    std::vector<uint8_t> used;std::vector<U> degree,prefix;
    std::unordered_set<uint64_t> binaries;std::vector<std::vector<U>> candidates;
    std::string line;
    while(std::getline(input,line)) {
      const char* p=line.c_str();while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;
      if(!*p||*p=='c')continue;
      if(*p=='p') {
        if(header)throw std::runtime_error("duplicate header");
        std::istringstream h(p);std::string marker,format;uint64_t n;
        if(!(h>>marker>>format>>n>>expected)||format!="cnf"||n>5000000)throw std::runtime_error("invalid header");
        variables=U(n);used.resize(n+1);degree.resize(n+1);header=true;continue;
      }
      if(!header)throw std::runtime_error("missing header");
      while(*p) {
        while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;if(!*p)break;
        char* end=nullptr;long lit=std::strtol(p,&end,10);
        if(end==p||lit>long(variables)||lit< -long(variables))throw std::runtime_error("invalid literal");p=end;
        if(lit) {
          U v=U(std::abs(lit));if(!used[v]){used[v]=1;++active;}
          if(length<16)prefix.push_back(2*v+(lit<0));++length;
        } else {
          ++clauses;
          if(exact&&length==2&&(prefix[0]>>1)!=(prefix[1]>>1)) {
            uint64_t pair=key(prefix[0],prefix[1]);
            if(binaries.size()>=2000000&&!binaries.count(pair))exact=false;
            else binaries.insert(pair);
          } else if(exact&&length>=3&&length<=16) {
            std::sort(prefix.begin(),prefix.end());bool distinct=true;
            for(size_t i=1;i<prefix.size();++i)if((prefix[i]>>1)==(prefix[i-1]>>1))distinct=false;
            if(distinct) {
              if(candidates.size()>=1000000)exact=false;else candidates.push_back(prefix);
            }
          }
          if(!exact){binaries.clear();binaries.rehash(0);std::vector<std::vector<U>>().swap(candidates);}
          prefix.clear();length=0;
        }
      }
    }
    if(!header||length||clauses!=expected)throw std::runtime_error("incomplete CNF");
    std::vector<double> values(7,NAN);values[6]=exact?1:0;
    if(exact) {
      std::sort(candidates.begin(),candidates.end());candidates.erase(std::unique(candidates.begin(),candidates.end()),candidates.end());
      uint64_t groups=0,group_literals=0,positive=0,covered=0,shared=0;
      for(const auto& c:candidates) {
        bool complete=true;
        for(size_t i=0;i<c.size()&&complete;++i)for(size_t j=i+1;j<c.size();++j)
          if(!binaries.count(key(c[i]^1,c[j]^1))){complete=false;break;}
        if(!complete)continue;
        ++groups;group_literals+=c.size();
        for(U l:c){positive+=!(l&1);++degree[l>>1];}
      }
      for(U v=1;v<=variables;++v){covered+=(degree[v]>0);shared+=(degree[v]>=2);}
      values[0]=active?double(covered)/active:0.;values[1]=active?double(groups)/active:0.;
      values[2]=groups?double(group_literals)/groups:NAN;values[3]=group_literals?double(positive)/group_literals:NAN;
      values[4]=covered?double(shared)/covered:0.;values[5]=candidates.size()?double(groups)/candidates.size():0.;
    }
    const char* names[]={"e_block_variable_fraction","e_blocks_per_variable","e_mean_block_size",
      "e_positive_block_literal_fraction","e_shared_variable_fraction","e_complete_block_fraction","e_exact"};
    std::cout<<std::setprecision(12)<<"{\"features\":{";
    for(size_t i=0;i<values.size();++i){if(i)std::cout<<",";std::cout<<"\""<<names[i]<<"\":";if(std::isfinite(values[i]))std::cout<<values[i];else std::cout<<"null";}
    std::cout<<"},\"parsed_variables\":"<<variables<<",\"parsed_clauses\":"<<clauses
      <<",\"feature_wall_s\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"}\n";
    return 0;
  }catch(const std::exception& e){std::cerr<<"choice feature error: "<<e.what()<<"\n";return 2;}
}
