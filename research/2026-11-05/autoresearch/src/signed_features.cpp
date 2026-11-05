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

int main(int argc, char **argv) {
  try {
    if (argc != 3) throw std::runtime_error("path and CPU budget required");
    double seconds = std::stod(argv[2]);
    itimerval timer{};
    timer.it_value.tv_sec = (int) seconds;
    timer.it_value.tv_usec = std::max(1, (int)((seconds-(int)seconds)*1e6));
    setitimer(ITIMER_PROF, &timer, nullptr);
    rlimit mem{1536ULL*1024*1024,1536ULL*1024*1024};
    setrlimit(RLIMIT_AS,&mem);
    std::ifstream f(argv[1], std::ios::binary);
    if (!f) throw std::runtime_error("input open failed");
    std::string text((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    const char *p=text.data(), *end=p+text.size();
    long long nv=-1,nc=-1,m=0,literals=0,empty=0,allpos=0,allneg=0;
    int k=0; bool pos=false,neg=false;
    long double weight=0,wp=0,wn=0;
    while(p<end) {
      if (*p==' ' || *p=='\t' || *p=='\n' || *p=='\r') {++p;continue;}
      if (*p=='c') {while(p<end && *p!='\n') ++p;continue;}
      if (*p=='p') {
        const char *a=p;while(p<end && *p!='\n') ++p;
        std::istringstream h(std::string(a,p));std::string tag,fmt,extra;
        if(nv>=0 || !(h>>tag>>fmt>>nv>>nc) || fmt!="cnf" || nv<0 || nc<0 || (h>>extra)) throw std::runtime_error("invalid header");
        continue;
      }
      bool negative=false;if(*p=='-'){negative=true;++p;}
      else if(*p=='+') ++p;
      if(p==end || *p<'0' || *p>'9') throw std::runtime_error("invalid token");
      long long lit=0;while(p<end && *p>='0' && *p<='9'){lit=lit*10+(*p-'0');++p;if(lit>2147483647LL)throw std::runtime_error("literal overflow");}
      if(lit) {if(nv<0 || lit>nv)throw std::runtime_error("literal out of header");++k;++literals;pos|=!negative;neg|=negative;}
      else {
        ++m;
        if(k==0)++empty;
        else {long double w=std::ldexp((long double)1,-std::min(k,32));weight+=w; if(!neg){++allpos;wp+=w;}if(!pos){++allneg;wn+=w;}}
        k=0;pos=neg=false;
      }
    }
    if(nv<0 || m!=nc || k)throw std::runtime_error("incomplete input");
    std::cout<<std::setprecision(17)<<"{\"clauses\":"<<m<<",\"literals\":"<<literals<<",\"empty_clauses\":"<<empty
      <<",\"positive_only_clause_fraction\":"<<(m?(double)allpos/m:0)
      <<",\"negative_only_clause_fraction\":"<<(m?(double)allneg/m:0)
      <<",\"signed_clause_bias\":"<<(m?(double)(allpos-allneg)/m:0)
      <<",\"weighted_signed_clause_bias\":"<<(weight?(double)((wp-wn)/weight):0)<<"}\n";
    return 0;
  } catch(const std::exception &e) {std::cerr<<e.what()<<"\n";return 2;}
}
