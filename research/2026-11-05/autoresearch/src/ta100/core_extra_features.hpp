#pragma once
// Independent bounded covered-literal and ITE mechanisms. No CNF rewrite or search.
#include "cnf_data.hpp"
#include <iterator>
#include <map>
#include <set>

namespace ta100_core_extra {
using ta100::CNF;using ta100::Clause;using ta100::Lit;using ta100::Block;
constexpr uint64_t CONTEXT=256,ENVIRONMENT=256,ITE_PROBES=CONTEXT*CONTEXT;
struct Budget {double deadline;explicit Budget(double seconds):deadline(ta100::cpu_now()+std::max(0.,seconds)){}
  bool done()const{return ta100::cpu_now()>=deadline;}};
inline std::vector<uint32_t> context(const CNF&f,size_t lower,size_t upper,Budget&budget,bool&complete) {
  std::vector<uint32_t> selected;selected.reserve(CONTEXT);complete=true;
  for(uint32_t c=0;c<f.clauses.size()&&selected.size()<CONTEXT;++c) {
    if((c&8191U)==0&&budget.done()){complete=false;break;}
    if(!f.tautological[c]&&f.clauses[c].size()>=lower&&f.clauses[c].size()<=upper)selected.push_back(c);
  }
  return selected;
}
inline bool taut_resolvent(const Clause&c,const Clause&d,Lit pivot) {
  for(Lit l:c)if(l!=pivot&&std::binary_search(d.begin(),d.end(),-l))return true;
  return false;
}
inline Block covered(const CNF&f,Budget&budget) {
  const std::string key="f_core_covered_intersection";bool complete;
  auto selected=context(f,2,8,budget,complete);
  if(!complete)return ta100::unavailable(key,"TIMEOUT","covered context selection budget");
  uint64_t work=0,eligible=0,offered=0,excluded=0;int64_t total_new_literals=0;
  for(uint32_t cid:selected) {
    const Clause&c=f.clauses[cid];
    for(Lit l:c) {
      ++offered;if(budget.done())return ta100::unavailable(key,"TIMEOUT","covered intersection budget",work);
      const auto&opposite=ta100::occurrences(f,-l);
      if(opposite.empty()||opposite.size()>ENVIRONMENT){++excluded;continue;}
      bool admitted=true;for(uint32_t did:opposite)if(f.clauses[did].size()>16){admitted=false;break;}
      if(!admitted){++excluded;continue;}
      Clause intersection;bool has_candidate=false;
      for(uint32_t did:opposite) {
        if((++work&63U)==0&&budget.done())return ta100::unavailable(key,"TIMEOUT","covered resolution-environment budget",work);
        const Clause&d=f.clauses[did];if(taut_resolvent(c,d,l))continue;
        Clause support;for(Lit x:d)if(x!=-l)support.push_back(x);
        if(!has_candidate){intersection=std::move(support);has_candidate=true;}
        else {
          Clause next;std::set_intersection(intersection.begin(),intersection.end(),support.begin(),support.end(),std::back_inserter(next));
          intersection.swap(next);
        }
        if(intersection.empty())break; // Later intersections cannot add literals.
      }
      if(!has_candidate)continue; // Empty RC is blockedness, not this mechanism.
      ++eligible;
      for(Lit x:intersection)if(!std::binary_search(c.begin(),c.end(),x))++total_new_literals;
    }
  }
  Block b=ta100::fraction(key,total_new_literals,eligible,work);
  b.reason="first256 non-taut width2..8 clauses; full opposite environment<=256/partnerwidth<=16; offered="+
    std::to_string(offered)+"; excluded_environments="+std::to_string(excluded);
  return b;
}
inline Clause canonical(Lit a,Lit b,Lit c) {Clause out={a,b,c};std::sort(out.begin(),out.end());return out;}
inline Block ite(const CNF&f,Budget&budget) {
  const std::string key="f_core_ite_output";bool complete;
  auto selected=context(f,3,3,budget,complete);
  if(!complete)return ta100::unavailable(key,"TIMEOUT","ITE context selection budget");
  std::set<Clause> clauses;std::set<uint32_t> variables,outputs;
  std::map<std::pair<Lit,Lit>,std::vector<Lit>> pair_other;
  for(uint32_t cid:selected) {
    const Clause&c=f.clauses[cid];clauses.insert(c);
    for(Lit l:c)variables.insert(uint32_t(std::abs(l)));
    for(int i=0;i<3;++i)for(int j=i+1;j<3;++j)pair_other[{c[i],c[j]}].push_back(c[3-i-j]);
  }
  uint64_t work=0;
  // Complete four-clause certificate for y <-> ITE(s,a,b):
  // (-s,-a,y),(-s,a,-y),(s,-b,y),(s,b,-y). All four variables distinct.
  for(const Clause&c:clauses)for(int i=0;i<3;++i)for(int j=0;j<3;++j)if(i!=j) {
    if(budget.done())return ta100::unavailable(key,"TIMEOUT","ITE template budget",work);
    Lit y=c[i],s=-c[j],a=-c[3-i-j];
    if(!clauses.count(canonical(-s,a,-y)))continue;
    auto pair=std::minmax(s,y);auto found=pair_other.find({pair.first,pair.second});
    if(found==pair_other.end())continue;
    for(Lit other:found->second) {
      if(++work>ITE_PROBES)return ta100::unavailable(key,"CAPPED","256x256 complete-template probes",work);
      Lit b=-other;
      if(std::abs(b)==std::abs(y)||std::abs(b)==std::abs(s)||std::abs(b)==std::abs(a))continue;
      if(clauses.count(canonical(s,b,-y)))outputs.insert(uint32_t(std::abs(y)));
    }
  }
  Block b=ta100::fraction(key,outputs.size(),variables.size(),work);
  b.reason="complete four-clause ITE certificates inside first256 non-taut ternary clauses; four distinct variables";
  return b;
}
inline std::vector<Block> compute(const CNF&f,double cpu_budget=1.0) {
  Budget budget(cpu_budget);std::vector<Block> result;
  double started=ta100::cpu_now();Block a=covered(f,budget);a.cpu_s=ta100::cpu_now()-started;result.push_back(std::move(a));
  started=ta100::cpu_now();Block b=ite(f,budget);b.cpu_s=ta100::cpu_now()-started;result.push_back(std::move(b));return result;
}
} // namespace ta100_core_extra
