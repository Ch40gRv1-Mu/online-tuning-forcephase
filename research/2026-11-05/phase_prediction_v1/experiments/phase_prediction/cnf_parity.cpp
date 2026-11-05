// Complete ternary parity-template structure, without solving or identities.
#include <algorithm>
#include <array>
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
#include <unordered_map>
#include <vector>
using U=uint32_t;
struct Triple {
  U a,b,c;
  bool operator==(const Triple& x)const{return a==x.a&&b==x.b&&c==x.c;}
};
struct Hash {
  size_t operator()(const Triple& x)const {
    uint64_t h=x.a*0x9e3779b97f4a7c15ULL;
    h^=x.b+0x9e3779b97f4a7c15ULL+(h<<6)+(h>>2);
    h^=x.c+0x9e3779b97f4a7c15ULL+(h<<6)+(h>>2);return size_t(h);
  }
};
int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("usage: cnf_parity INPUT.cnf");
    auto start=std::chrono::steady_clock::now();
    std::ifstream input(argv[1]);if(!input)throw std::runtime_error("cannot open input");
    U variables=0;uint64_t expected=0,clauses=0,active=0,ternaries=0,length=0;
    bool header=false,exact=true;std::vector<uint8_t> used;std::vector<U> degree;
    std::unordered_map<Triple,uint8_t,Hash> masks;
    std::array<int,3> prefix{};std::string line;
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
        if(end==p||lit>long(variables)||lit< -long(variables))throw std::runtime_error("invalid literal");
        p=end;
        if(lit) {
          U v=U(std::abs(lit));if(!used[v]){used[v]=1;++active;}
          if(length<3)prefix[length]=int(lit);++length;
        } else {
          ++clauses;ternaries+=(length==3);
          if(exact&&length==3) {
            auto c=prefix;std::sort(c.begin(),c.end(),[](int a,int b){return std::abs(a)<std::abs(b);});
            if(std::abs(c[0])!=std::abs(c[1])&&std::abs(c[1])!=std::abs(c[2])) {
              Triple t{U(std::abs(c[0])),U(std::abs(c[1])),U(std::abs(c[2]))};
              auto it=masks.find(t);
              if(it==masks.end()&&masks.size()>=2000000) {exact=false;masks.clear();masks.rehash(0);}
              else {
                U sign=(c[0]<0)|((c[1]<0)<<1)|((c[2]<0)<<2);
                if(it==masks.end())masks.emplace(t,uint8_t(1U<<sign));else it->second|=uint8_t(1U<<sign);
              }
            }
          }
          length=0;
        }
      }
    }
    if(!header||length||clauses!=expected)throw std::runtime_error("incomplete CNF");
    std::vector<double> values(7,NAN);values[6]=exact?1:0;
    if(exact) {
      uint64_t templates=0,even=0,covered=0,shared=0;U maxdegree=0;
      for(auto entry:masks) {
        bool e=(entry.second&0x69)==0x69,o=(entry.second&0x96)==0x96;
        if(e==o)continue;
        ++templates;even+=e;
        for(U v:{entry.first.a,entry.first.b,entry.first.c})++degree[v];
      }
      for(U v=1;v<=variables;++v) {
        covered+=(degree[v]>0);shared+=(degree[v]>=2);maxdegree=std::max(maxdegree,degree[v]);
      }
      values[0]=active?double(covered)/active:0.;values[1]=active?double(templates)/active:0.;
      values[2]=templates?double(even)/templates:NAN;values[3]=covered?double(shared)/covered:0.;
      values[4]=maxdegree;values[5]=ternaries?4.*templates/ternaries:0.;
    }
    const char* names[]={"p_parity_variable_fraction","p_templates_per_variable","p_forbidden_even_fraction",
      "p_shared_variable_fraction","p_max_template_degree","p_clause_coverage","p_exact"};
    std::cout<<std::setprecision(12)<<"{\"features\":{";
    for(size_t i=0;i<values.size();++i) {
      if(i)std::cout<<",";std::cout<<"\""<<names[i]<<"\":";
      if(std::isfinite(values[i]))std::cout<<values[i];else std::cout<<"null";
    }
    std::cout<<"},\"parsed_variables\":"<<variables<<",\"parsed_clauses\":"<<clauses
      <<",\"feature_wall_s\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"}\n";
    return 0;
  }catch(const std::exception& e){std::cerr<<"parity feature error: "<<e.what()<<"\n";return 2;}
}
