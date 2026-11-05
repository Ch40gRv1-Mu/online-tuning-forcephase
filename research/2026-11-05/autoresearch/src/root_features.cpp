#include <sys/time.h>
#include <sys/resource.h>
#include <cmath>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>
#include <stdexcept>
#include <cstdlib>

int main(int argc,char **argv) {
 try {
  if(argc!=3)throw std::runtime_error("path and budget required");
  double seconds=std::stod(argv[2]);itimerval timer{};
  timer.it_value.tv_sec=(int)seconds;timer.it_value.tv_usec=std::max(1,(int)((seconds-(int)seconds)*1e6));
  setitimer(ITIMER_PROF,&timer,nullptr);
  rlimit mem{1536ULL*1024*1024,1536ULL*1024*1024};setrlimit(RLIMIT_AS,&mem);
  std::ifstream f(argv[1],std::ios::binary);if(!f)throw std::runtime_error("input open failed");
  std::string text((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
  const char *p=text.data(),*end=p+text.size();
  int nv=-1,nc=-1;std::vector<std::vector<int>> clauses;std::vector<int> clause;
  while(p<end) {
   if(*p==' '||*p=='\t'||*p=='\n'||*p=='\r'){++p;continue;}
   if(*p=='c'){while(p<end&&*p!='\n')++p;continue;}
   if(*p=='p') {
    const char *a=p;while(p<end&&*p!='\n')++p;
    std::istringstream h(std::string(a,p));std::string tag,fmt,extra;
    if(nv>=0||!(h>>tag>>fmt>>nv>>nc)||fmt!="cnf"||nv<0||nc<0||(h>>extra))throw std::runtime_error("invalid header");
    clauses.reserve(nc);continue;
   }
   bool neg=false;if(*p=='-'){neg=true;++p;}else if(*p=='+')++p;
   if(p==end||*p<'0'||*p>'9')throw std::runtime_error("invalid literal");
   long long lit=0;while(p<end&&*p>='0'&&*p<='9'){lit=lit*10+(*p-'0');++p;if(lit>2147483647LL)throw std::runtime_error("literal overflow");}
   if(lit){if(nv<0||lit>nv)throw std::runtime_error("literal exceeds header");clause.push_back(neg?-(int)lit:(int)lit);}
   else {clauses.push_back(std::move(clause));clause.clear();}
  }
  if(nv<0||!clause.empty()||(int)clauses.size()!=nc)throw std::runtime_error("incomplete CNF");
  std::vector<std::vector<int>> occ(2*(size_t(nv)+1));
  std::vector<int> remaining(nc),queue,seen(2*(size_t(nv)+1),-1);std::vector<signed char> values(nv+1,0);
  std::vector<unsigned char> satisfied(nc,0),active(nv+1,0),ractive(nv+1,0);
  auto idx=[](int lit){return 2*std::abs(lit)+(lit<0);};
  long long literals=0,negative=0,binary=0,empty=0;bool conflict=false;
  for(int i=0;i<nc;++i) {
   auto &c=clauses[i];binary+=c.size()==2;
   if(c.empty()){++empty;conflict=true;}
   for(int lit:c){active[std::abs(lit)]=1;++literals;negative+=lit<0;}
   std::vector<int> clean;clean.reserve(c.size());bool tautology=false;
   for(int lit:c){if(seen[idx(-lit)]==i)tautology=true;if(seen[idx(lit)]!=i){clean.push_back(lit);seen[idx(lit)]=i;}}
   if(tautology){c.clear();remaining[i]=0;satisfied[i]=1;continue;}
   c=std::move(clean);remaining[i]=c.size();
   if(c.size()==1)queue.push_back(c[0]);
   for(int lit:c)occ[idx(lit)].push_back(i);
  }
  for(size_t q=0;q<queue.size()&&!conflict;++q) {
   int lit=queue[q],v=std::abs(lit),sign=lit>0?1:-1;
   if(values[v]){if(values[v]!=sign)conflict=true;continue;}
   values[v]=sign;
   for(int ci:occ[idx(lit)])satisfied[ci]=1;
   for(int ci:occ[idx(-lit)]) {
    if(satisfied[ci])continue;
    --remaining[ci];
    if(remaining[ci]==0){conflict=true;break;}
    if(remaining[ci]==1) {
     bool found=false;
     for(int x:clauses[ci])if(!values[std::abs(x)]){queue.push_back(x);found=true;break;}
     if(!found){conflict=true;break;}
    }
   }
  }
  long long av=0,assigned=0,rm=0,rl=0,rneg=0,rbinary=0,rav=0;
  long double w=0,wp=0,wn=0;
  for(int v=1;v<=nv;++v){av+=active[v]!=0;assigned+=active[v]&&values[v];}
  for(int ci=0;ci<nc;++ci) {
   auto &c=clauses[ci];if(satisfied[ci])continue;
   int k=0;bool pos=false,neg=false;
   for(int lit:c)if(!values[std::abs(lit)]){++k;++rl;rneg+=lit<0;pos|=lit>0;neg|=lit<0;ractive[std::abs(lit)]=1;}
   ++rm;rbinary+=k==2;
   if(k){long double z=std::ldexp((long double)1,-std::min(k,32));w+=z;if(!neg)wp+=z;if(!pos)wn+=z;}
  }
  for(int v=1;v<=nv;++v)rav+=ractive[v]!=0;
  std::cout<<std::setprecision(17)<<"{\"clauses\":"<<nc<<",\"literals\":"<<literals<<",\"empty_clauses\":"<<empty
    <<",\"active_variables\":"<<av<<",\"root_assigned_variables\":"<<assigned<<",\"root_remaining_clauses\":"<<rm
    <<",\"root_conflict\":"<<(conflict?"true":"false")<<",\"usable_residual\":"<<(!conflict&&rm>0&&rl>0?"true":"false")
    <<",\"residual_active_variable_fraction\":"<<(av?(double)rav/av:0)
    <<",\"residual_clause_fraction\":"<<(nc?(double)rm/nc:0)
    <<",\"delta_binary_fraction\":"<<((rm?(double)rbinary/rm:0)-(nc?(double)binary/nc:0))
    <<",\"delta_negative_literal_fraction\":"<<((rl?(double)rneg/rl:0)-(literals?(double)negative/literals:0))
    <<",\"residual_weighted_signed_clause_bias\":"<<(w?(double)((wp-wn)/w):0)<<"}\n";
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}
}
