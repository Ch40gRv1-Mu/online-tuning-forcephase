// R33: pinned CaDiCaL, root UP then one no-search elimination round.
#include "cadical.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <sys/resource.h>
#include <unistd.h>
#include <vector>

struct MemoryGuard : CaDiCaL::Terminator {
  bool exceeded=false;
  bool terminate() override {
    rusage usage;
    if(getrusage(RUSAGE_SELF,&usage))return false;
#ifdef __APPLE__
    const unsigned long long bytes=usage.ru_maxrss;
#else
    const unsigned long long bytes=1024ULL*usage.ru_maxrss;
#endif
    exceeded=exceeded||bytes>1024ULL*1024*1024;
    return exceeded;
  }
};

struct Summary : CaDiCaL::ClauseIterator {
  long long m=0, literals=0, binary=0, ternary=0, longc=0;
  long long horn=0, invhorn=0, purepos=0, pureneg=0, positive=0;
  double balance=0;
  std::vector<long long> degrees;
  explicit Summary(int n):degrees(n+1,0) {}
  bool clause(const std::vector<int>& c) override {
    // Empty clauses are not exposed as an explicit result/UNSAT feature.
    if (c.empty()) return true;
    ++m; const long long width=c.size(); literals+=width;
    long long pos=0;
    for (int lit:c) {
      const int var=std::abs(lit);
      if(var>=int(degrees.size())) throw std::runtime_error("unexpected fresh variable");
      ++degrees[var]; pos+=lit>0;
    }
    const long long neg=width-pos;
    binary+=width==2; ternary+=width==3; longc+=width>=4;
    horn+=pos<=1; invhorn+=neg<=1; purepos+=neg==0; pureneg+=pos==0;
    positive+=pos; balance+=double(std::min(pos,neg))/std::max(pos,neg);
    return true;
  }
  std::vector<double> vector() const {
    long long n=0; double sum=0,sumsq=0;
    for(long long d:degrees) if(d) {++n;sum+=d;sumsq+=double(d)*d;}
    const double den=std::max(m,1LL), mean=n?sum/n:0;
    const double cv2=mean>0?std::max(0.,sumsq/std::max(n,1LL)-mean*mean)/(mean*mean):0;
    return {std::log1p(n),std::log1p(m),std::log1p(literals),std::log1p(double(literals)/den),
      binary/den,ternary/den,longc/den,horn/den,invhorn/den,purepos/den,pureneg/den,
      double(positive)/std::max(literals,1LL),balance/den,std::log1p(cv2)};
  }
};

static void json_vector(const std::vector<double>& values) {
  std::cout<<'[';
  for(size_t i=0;i<values.size();++i) {if(i)std::cout<<',';if(!std::isfinite(values[i]))throw std::runtime_error("nonfinite feature");std::cout<<values[i];}
  std::cout<<']';
}

int main() {
  rlimit core={0,0}, cpu={4,5};
  setrlimit(RLIMIT_CORE,&core);
  if(setrlimit(RLIMIT_CPU,&cpu))return 70;
  alarm(6);
  try {
    MemoryGuard guard;
    CaDiCaL::Solver solver;
    // The pinned library was compiled with QUIET, which omits this option.
    if(solver.is_valid_option("quiet"))solver.set("quiet",1);
    // No speculative assignments, local walk, SAT sweeping or kitten search.
    for(const char* name:{"probe","inprobing","sweep","vivify","walk","lucky",
        "luckyearly","luckylate","elimdef","condition","cover","block","factor","preprocesslight"})
      if(!solver.set(name,0))throw std::runtime_error(std::string("pinned option unavailable: ")+name);
    if(!solver.set("phase",1)||!solver.set("forcephase",0))throw std::runtime_error("phase unavailable");
    solver.connect_terminator(&guard);
    int vars=0;
    const char* error=solver.read_dimacs(stdin,"<stdin>",vars,1);
    if(error)throw std::runtime_error(error);
    if(vars>100000)throw std::runtime_error("input count bound");
    if(guard.terminate())throw std::runtime_error("preprocess RSS threshold");
    // Return codes are deliberately discarded, never labels or routing input.
    (void)solver.simplify(0);
    if(guard.exceeded)throw std::runtime_error("preprocess RSS threshold");
    if(solver.get_statistic_value("decisions")!=0)throw std::runtime_error("UP performed decisions");
    Summary up(vars); solver.traverse_clauses(up);
    const auto n0=solver.active();
    const auto fixed0=solver.get_statistic_value("fixed");
    const auto elim0=solver.get_statistic_value("eliminated");
    const auto subst0=solver.get_statistic_value("subsitutued"); // Public pinned API spelling.
    (void)solver.simplify(1);
    if(guard.exceeded)throw std::runtime_error("preprocess RSS threshold");
    if(solver.get_statistic_value("decisions")!=0)throw std::runtime_error("preprocessor performed decisions");
    Summary post(vars); solver.traverse_clauses(post);
    const auto n1=solver.active();
    const double denom=std::max(n0,1);
    std::vector<double> change={double(n1)/denom,double(post.m)/std::max(up.m,1LL),
      double(post.literals)/std::max(up.literals,1LL),
      (solver.get_statistic_value("fixed")-fixed0)/denom,
      (solver.get_statistic_value("eliminated")-elim0)/denom,
      (solver.get_statistic_value("subsitutued")-subst0)/denom};
    std::cout<<std::setprecision(17)<<"{\"schema\":\"forcephase.preprocess_structure.v1\",\"decisions\":0,\"UP\":";
    json_vector(up.vector()); std::cout<<",\"post\":";json_vector(post.vector());
    std::cout<<",\"change\":";json_vector(change);std::cout<<"}\n";
    return 0;
  } catch(const std::exception& e) {std::cerr<<e.what()<<'\n'; return 2;}
}
