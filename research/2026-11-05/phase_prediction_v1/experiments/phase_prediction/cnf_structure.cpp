// Input-only numeric features. No names, family labels or outcome information.
// g++ -O3 -std=c++17 cnf_structure.cpp -o cnf_structure
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
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

using U = uint32_t;
static uint64_t pair_key(U a, U b) { if (a > b) std::swap(a,b); return (uint64_t(a)<<32)|b; }
static U literal_code(int l) { return U(2*std::abs(l)+(l<0)); }

struct Features {
  U declared=0; uint64_t declared_clauses=0, clauses=0, literals=0, incidences=0;
  uint64_t positive=0, horn=0, antihorn=0, active=0, components=0, empty=0;
  uint64_t unit=0, binary=0, ternary=0, long_clause=0, max_len=0;
  long double len2=0, jw_pos=0, jw_all=0;
  std::array<uint64_t,7> lengths{};
  std::vector<U> parent,size,degree,occ,pos,stamp;
  std::vector<std::array<U,3>> ternaries;
  std::unordered_set<uint64_t> binaries;
  bool motifs_exact=true; const size_t motif_cap=2000000;

  U root(U v) { while(parent[v]!=v) { parent[v]=parent[parent[v]]; v=parent[v]; } return v; }
  void join(U a,U b) { a=root(a); b=root(b); if(a==b)return;
    if(size[a]<size[b])std::swap(a,b); parent[b]=a; size[a]+=size[b]; --components; }
  void init(U n) {
    if(n>5000000)throw std::runtime_error("declared variable cap exceeded (5 million)");
    declared=n; parent.resize(n+1);size.resize(n+1);degree.resize(n+1);
    occ.resize(n+1);pos.resize(n+1);stamp.resize(n+1);
  }
  void add(const std::vector<int>& c) {
    ++clauses; if(clauses>=UINT32_MAX)throw std::runtime_error("too many clauses");
    uint64_t n=c.size(),np=0; U first=0;
    for(int l:c) {
      U v=std::abs(l); if(!v||v>declared)throw std::runtime_error("literal outside header");
      if(!occ[v]) { parent[v]=v;size[v]=1; ++active; ++components; }
      ++occ[v]; if(l>0){++pos[v];++np;}
      if(stamp[v]!=clauses) {stamp[v]=U(clauses);++degree[v];++incidences;
        if(first)join(first,v);else first=v;}
    }
    literals+=n;positive+=np;len2+=n*n;horn+=(np<=1);antihorn+=(n-np<=1);
    empty+=(n==0);unit+=(n==1);binary+=(n==2);ternary+=(n==3);long_clause+=(n>=5);
    max_len=std::max(max_len,n);
    size_t bin=n<=4?n:(n<=8?5:6);++lengths[bin];
    long double weight=std::ldexp(1.0L,-int(std::min<uint64_t>(n,10000)));
    jw_pos+=weight*np;jw_all+=weight*n;
    if(n==2 && std::abs(c[0])!=std::abs(c[1])) {
      if(binaries.size()<motif_cap)binaries.insert(pair_key(literal_code(c[0]),literal_code(c[1])));
      else motifs_exact=false;
    }
    if(n==3 && std::abs(c[0])!=std::abs(c[1]) && std::abs(c[0])!=std::abs(c[2]) && std::abs(c[1])!=std::abs(c[2])) {
      if(ternaries.size()<motif_cap)ternaries.push_back({literal_code(c[0]),literal_code(c[1]),literal_code(c[2])});
      else motifs_exact=false;
    }
  }
  void print(double elapsed) {
    std::vector<U> degrees;long double d2=0,entropy=0,imbalance=0;
    uint64_t leaves=0,deg2=0,pure=0,largest=0;
    for(U v=1;v<=declared;++v)if(occ[v]) {
      degrees.push_back(degree[v]);d2+=uint64_t(degree[v])*degree[v];
      leaves+=(degree[v]==1);deg2+=(degree[v]==2);pure+=(pos[v]==0||pos[v]==occ[v]);
      imbalance+=std::abs(double(2.0*pos[v]-occ[v]))/occ[v];
      double p=double(degree[v])/std::max<uint64_t>(1,incidences);entropy-=p*std::log(std::max(p,1e-300));
      if(parent[v]==v)largest=std::max<uint64_t>(largest,size[v]);
    }
    std::sort(degrees.begin(),degrees.end());
    auto divide=[](long double a,long double b){return b>0?double(a/b):0.0;};
    double dm=divide(incidences,active),lm=divide(literals,clauses);
    uint64_t cycles=incidences+components+empty-active-clauses;
    uint64_t gates=0;
    if(motifs_exact)for(auto c:ternaries)for(int i=0;i<3;++i)
      gates+=binaries.count(pair_key(c[i]^1,c[(i+1)%3]^1)) && binaries.count(pair_key(c[i]^1,c[(i+2)%3]^1));
    bool first=true;std::cout<<std::setprecision(12)<<"{";
    auto emit=[&](const char* k,double value){if(!first)std::cout<<",";first=false;
      std::cout<<"\""<<k<<"\":";if(std::isfinite(value))std::cout<<value;else std::cout<<"null";};
    emit("s_header_variables",declared);emit("s_variables",active);emit("s_clauses",clauses);
    emit("s_log_variables",std::log1p(active));emit("s_log_clauses",std::log1p(clauses));
    emit("s_cv_ratio",divide(clauses,active));emit("s_mean_length",lm);
    emit("s_length_std",std::sqrt(std::max(0.0,divide(len2,clauses)-lm*lm)));
    emit("s_max_length",max_len);emit("s_unit_fraction",divide(unit,clauses));
    emit("s_binary_fraction",divide(binary,clauses));emit("s_ternary_fraction",divide(ternary,clauses));
    emit("s_long_fraction",divide(long_clause,clauses));emit("s_empty_fraction",divide(empty,clauses));
    emit("s_positive_fraction",divide(positive,literals));emit("s_horn_fraction",divide(horn,clauses));
    emit("s_antihorn_fraction",divide(antihorn,clauses));emit("s_pure_variable_fraction",divide(pure,active));
    emit("s_mean_polarity_imbalance",divide(imbalance,active));emit("s_jw_positive_fraction",divide(jw_pos,jw_all));
    emit("g_components",components+empty);emit("g_largest_component_fraction",divide(largest,active));
    emit("g_cycle_excess",cycles);emit("g_cycle_excess_per_incidence",divide(cycles,incidences));
    emit("g_leaf_variable_fraction",divide(leaves,active));emit("g_degree_two_fraction",divide(deg2,active));
    emit("g_degree_mean",dm);emit("g_degree_cv",dm>0?std::sqrt(std::max(0.0,divide(d2,active)-dm*dm))/dm:0);
    emit("g_degree_p50",degrees.empty()?0:degrees[(degrees.size()-1)/2]);
    emit("g_degree_p90",degrees.empty()?0:degrees[(degrees.size()-1)*9/10]);
    emit("g_degree_max",degrees.empty()?0:degrees.back());
    emit("g_degree_entropy_normalized",active>1?double(entropy)/std::log(active):0);
    emit("g_gate_motif_fraction",motifs_exact?divide(gates,ternary):NAN);
    emit("g_gate_motifs_exact",motifs_exact?1:0);
    emit("feature_wall_s",elapsed);std::cout<<"}\n";
  }
};

int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("usage: cnf_structure INPUT.cnf");
    auto start=std::chrono::steady_clock::now();
    std::ifstream input(argv[1]);if(!input)throw std::runtime_error("cannot open input");
    Features f;bool header=false;std::vector<int> clause;std::string line;
    while(std::getline(input,line)) {
      const char* p=line.c_str();while(*p && std::isspace(static_cast<unsigned char>(*p)))++p;
      if(!*p||*p=='c')continue;
      if(*p=='p') {
        if(header)throw std::runtime_error("duplicate header");
        std::istringstream h(p);std::string marker,format;uint64_t n,m;
        if(!(h>>marker>>format>>n>>m)||format!="cnf"||n>5000000)throw std::runtime_error("invalid or oversized header");
        f.init(U(n));f.declared_clauses=m;header=true;continue;
      }
      if(!header)throw std::runtime_error("missing header");
      while(*p) {
        while(*p && std::isspace(static_cast<unsigned char>(*p)))++p;
        if(!*p)break;char* end=nullptr;long lit=std::strtol(p,&end,10);
        if(end==p||lit>5000000||lit< -5000000)throw std::runtime_error("bad literal");
        p=end;if(lit)clause.push_back(int(lit));else{f.add(clause);clause.clear();}
      }
    }
    if(!header||!clause.empty()||f.clauses!=f.declared_clauses)throw std::runtime_error("incomplete CNF or wrong clause count");
    f.print(std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count());
    return 0;
  }catch(const std::exception& e){std::cerr<<"feature error: "<<e.what()<<"\n";return 2;}
}
