// Binary-clause literal implications; no solver, names, answers or gate labels.
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
#include <utility>
#include <vector>
using U=uint32_t;
using Edge=std::pair<U,U>;
struct CSR {
  std::vector<U> off,adj;
  CSR(U n,const std::vector<Edge>& edges,bool reverse):off(n+1),adj(edges.size()) {
    for(auto e:edges)++off[(reverse?e.second:e.first)+1];
    for(U i=0;i<n;++i)off[i+1]+=off[i];
    auto next=off;
    for(auto e:edges)adj[next[reverse?e.second:e.first]++]=reverse?e.first:e.second;
  }
};

int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("usage: cnf_implication INPUT.cnf");
    auto start=std::chrono::steady_clock::now();
    std::ifstream input(argv[1]);if(!input)throw std::runtime_error("cannot open input");
    U variables=0;uint64_t expected=0,clauses=0,active=0;bool header=false,exact=true;
    std::vector<uint8_t> used;std::vector<Edge> edges;
    uint64_t length=0;int first=0,second=0;std::string line;
    while(std::getline(input,line)) {
      const char* p=line.c_str();while(*p && std::isspace(static_cast<unsigned char>(*p)))++p;
      if(!*p||*p=='c')continue;
      if(*p=='p') {
        if(header)throw std::runtime_error("duplicate header");
        std::istringstream h(p);std::string marker,format;uint64_t n;
        if(!(h>>marker>>format>>n>>expected)||format!="cnf"||n>5000000)throw std::runtime_error("invalid header");
        variables=U(n);used.resize(variables+1);header=true;continue;
      }
      if(!header)throw std::runtime_error("missing header");
      while(*p) {
        while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;if(!*p)break;
        char* end=nullptr;long lit=std::strtol(p,&end,10);
        if(end==p||lit>long(variables)||lit< -long(variables))throw std::runtime_error("invalid literal");
        p=end;
        if(lit) {
          U v=U(std::abs(lit));if(!used[v]){used[v]=1;++active;}
          if(length==0)first=int(lit);else if(length==1)second=int(lit);++length;
        } else {
          ++clauses;
          if(exact && length==2 && std::abs(first)!=std::abs(second)) {
            U a=2*U(std::abs(first))+(first<0),b=2*U(std::abs(second))+(second<0);
            if(edges.size()+2>4000000) {exact=false;std::vector<Edge>().swap(edges);}
            else {edges.emplace_back(a^1,b);edges.emplace_back(b^1,a);}
          }
          length=0;
        }
      }
    }
    if(!header||length||clauses!=expected)throw std::runtime_error("incomplete CNF");
    std::vector<double> values(8,NAN);values[7]=exact?1:0;
    if(exact) {
      std::sort(edges.begin(),edges.end());edges.erase(std::unique(edges.begin(),edges.end()),edges.end());
      U n=2*(variables+1);CSR forward(n,edges,false),reverse(n,edges,true);
      std::vector<uint8_t> seen(n);std::vector<U> order;
      std::vector<std::pair<U,U>> stack;
      for(U s=2;s<n;++s)if((forward.off[s+1]>forward.off[s]||reverse.off[s+1]>reverse.off[s])&&!seen[s]) {
        seen[s]=1;stack.emplace_back(s,forward.off[s]);
        while(!stack.empty()) {
          U v=stack.back().first;U& pos=stack.back().second;
          if(pos<forward.off[v+1]) {
            U w=forward.adj[pos++];if(!seen[w]){seen[w]=1;stack.emplace_back(w,forward.off[w]);}
          } else {order.push_back(v);stack.pop_back();}
        }
      }
      std::vector<U> comp(n,UINT32_MAX),sizes,work;
      for(auto it=order.rbegin();it!=order.rend();++it)if(comp[*it]==UINT32_MAX) {
        U id=U(sizes.size()),size=0;work.push_back(*it);comp[*it]=id;
        while(!work.empty()) {
          U v=work.back();work.pop_back();++size;
          for(U k=reverse.off[v];k<reverse.off[v+1];++k) {
            U w=reverse.adj[k];if(comp[w]==UINT32_MAX){comp[w]=id;work.push_back(w);}
          }
        }
        sizes.push_back(size);
      }
      values[0]=active?double(order.size())/(2*active):0.;
      if(!edges.empty()) {
        std::vector<Edge> dag_edges;std::vector<U> indeg(sizes.size());uint64_t positive_edges=0;
        for(auto e:edges) {
          positive_edges+=!(e.first&1);U a=comp[e.first],b=comp[e.second];
          if(a!=b){dag_edges.emplace_back(a,b);++indeg[b];}
        }
        CSR dag(U(sizes.size()),dag_edges,false);std::vector<U> topo,depth(sizes.size());
        std::vector<uint8_t> source(sizes.size());
        for(U i=0;i<sizes.size();++i)if(!indeg[i]){source[i]=1;topo.push_back(i);}
        for(size_t i=0;i<topo.size();++i)for(U k=dag.off[topo[i]];k<dag.off[topo[i]+1];++k)
          if(!--indeg[dag.adj[k]])topo.push_back(dag.adj[k]);
        if(topo.size()!=sizes.size())throw std::runtime_error("condensation is not acyclic");
        for(auto it=topo.rbegin();it!=topo.rend();++it)for(U k=dag.off[*it];k<dag.off[*it+1];++k)
          depth[*it]=std::max(depth[*it],depth[dag.adj[k]]+1);
        uint64_t cyclic=0;for(U s:sizes)if(s>1)cyclic+=s;
        uint64_t sources=0,pos_sources=0,pos_depth=0,neg_depth=0,pos_count=0,neg_count=0;
        for(U v:order) {
          if(source[comp[v]]){++sources;pos_sources+=!(v&1);}
          if(v&1){neg_depth+=depth[comp[v]];++neg_count;}
          else {pos_depth+=depth[comp[v]];++pos_count;}
        }
        double a=double(pos_depth)/pos_count,b=double(neg_depth)/neg_count;
        values[1]=double(cyclic)/order.size();values[2]=double(*std::max_element(sizes.begin(),sizes.end()))/order.size();
        values[3]=*std::max_element(depth.begin(),depth.end());values[4]=double(pos_sources)/sources;
        values[5]=(a-b)/(1+a+b);values[6]=double(positive_edges)/edges.size();
      }
    }
    const char* names[]={"b_binary_variable_fraction","b_scc_cyclic_fraction","b_largest_scc_fraction",
      "b_condensation_depth","b_positive_source_fraction","b_signed_depth_asymmetry",
      "b_positive_implication_edge_fraction","b_exact"};
    std::cout<<std::setprecision(12)<<"{\"features\":{";
    for(size_t i=0;i<values.size();++i) {
      if(i)std::cout<<",";std::cout<<"\""<<names[i]<<"\":";
      if(std::isfinite(values[i]))std::cout<<values[i];else std::cout<<"null";
    }
    std::cout<<"},\"parsed_variables\":"<<variables<<",\"parsed_clauses\":"<<clauses
      <<",\"feature_wall_s\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"}\n";
    return 0;
  }catch(const std::exception& e){std::cerr<<"implication feature error: "<<e.what()<<"\n";return 2;}
}
