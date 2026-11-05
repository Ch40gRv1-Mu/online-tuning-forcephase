#include "propagation_features.hpp"
#include <sys/time.h>
#include <sys/resource.h>
#include <iomanip>
#include <iostream>

static uint64_t splitmix64(uint64_t x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}

int main(int argc,char **argv){
 try{
  if(argc!=4)throw std::runtime_error("path budget seed required");
  double seconds=std::stod(argv[2]);itimerval timer{};timer.it_value.tv_sec=(int)seconds;timer.it_value.tv_usec=std::max(1,(int)((seconds-(int)seconds)*1e6));setitimer(ITIMER_PROF,&timer,nullptr);
  rlimit mem{1536ULL*1024*1024,1536ULL*1024*1024};setrlimit(RLIMIT_AS,&mem);
  uint64_t seed=std::stoull(argv[3]);PropagationFormula f(argv[1]);auto root=f.root();int remaining=f.remaining(root);
  auto free=f.free_variables(root);std::vector<std::pair<uint64_t,int>> ranks;
  if(!root.conflict&&remaining>0)for(int v:free)ranks.emplace_back(splitmix64(seed^uint64_t(v)),v);
  int pairs=std::min(size_t(3),ranks.size());std::partial_sort(ranks.begin(),ranks.begin()+pairs,ranks.end());
  struct Branch{int variable,sign,assigned,remaining;bool conflict;};std::vector<Branch> branches;
  bool directly_solved=root.conflict||remaining==0;double conflicts=0,gain=0,signed_gain=0,absolute_gain=0,clause_asym=0;
  for(int i=0;i<pairs;++i){
   int v=ranks[i].second;auto positive=f.propagate(root,{v});auto negative=f.propagate(root,{-v});
   for(auto *s:{&positive,&negative}){
    for(int x=1;x<=f.nv;++x)if(root.assigned[x]&&root.assigned[x]!=s->assigned[x])throw std::runtime_error("root assignment changed");
    if(s->assigned_count<root.assigned_count||s->assigned_count-root.assigned_count>(int)free.size())throw std::runtime_error("invalid assignment gain");
   }
   if(positive.assigned[v]!=1||negative.assigned[v]!=-1)throw std::runtime_error("branch unit lost");
   int rp=f.remaining(positive),rn=f.remaining(negative),gp=positive.assigned_count-root.assigned_count,gn=negative.assigned_count-root.assigned_count;
   branches.push_back({v,1,positive.assigned_count,rp,positive.conflict});branches.push_back({v,-1,negative.assigned_count,rn,negative.conflict});
   directly_solved|=(positive.conflict&&negative.conflict)||(!positive.conflict&&rp==0)||(!negative.conflict&&rn==0);
   conflicts+=positive.conflict+negative.conflict;gain+=gp+gn;signed_gain+=gp-gn;absolute_gain+=std::abs(gp-gn);
   clause_asym+=(negative.conflict?0:rn)-(positive.conflict?0:rp);
  }
  bool usable=!directly_solved&&pairs>0;
  std::cout<<std::setprecision(17)<<"{\"clauses\":"<<f.nc<<",\"literals\":"<<f.literals<<",\"empty_clauses\":"<<f.empty_clauses<<",\"root_assigned_variables\":"<<root.assigned_count<<",\"root_remaining_clauses\":"<<remaining<<",\"root_conflict\":"<<(root.conflict?"true":"false")<<",\"root_free_variables\":"<<free.size()<<",\"directly_solved_diagnostic\":"<<(directly_solved?"true":"false")<<",\"usable_branch\":"<<(usable?"true":"false")<<",\"branch_pairs\":"<<pairs;
  double denom=std::max(size_t(1),free.size()),pc=std::max(1,pairs);
  std::cout<<",\"branch_conflict_fraction\":"<<conflicts/(2*pc)<<",\"mean_assigned_gain_fraction\":"<<gain/(2*pc*denom)<<",\"signed_assigned_asymmetry\":"<<signed_gain/(pc*denom)<<",\"absolute_assigned_asymmetry\":"<<absolute_gain/(pc*denom)<<",\"signed_clause_asymmetry\":"<<clause_asym/(pc*std::max(1,remaining))<<",\"branches\":[";
  for(size_t i=0;i<branches.size();++i){if(i)std::cout<<",";auto &b=branches[i];std::cout<<"{\"variable\":"<<b.variable<<",\"sign\":"<<b.sign<<",\"assigned\":"<<b.assigned<<",\"remaining_clauses\":"<<b.remaining<<",\"conflict\":"<<(b.conflict?"true":"false")<<"}";}
  std::cout<<"]}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}
}
