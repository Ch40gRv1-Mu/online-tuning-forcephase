// TA100 core: ten input mechanisms, one parse; no UP, conditioning or SAT search.
#include "cnf_data.hpp"
#include <functional>
#include <unordered_map>

namespace {
using namespace ta100;
constexpr uint64_t INDEX_CAP=1000000, SUBSET_CAP=2000000;
constexpr uint64_t PAIR_CAP=200000, BCE_CAP=2000000, TWIN_CAP=2000000;
struct HashClause {
  size_t operator()(const Clause&c)const {
    uint64_t h=0x9e3779b97f4a7c15ULL;
    for(Lit l:c)h^=uint64_t(uint32_t(l))+0x9e3779b97f4a7c15ULL+(h<<6)+(h>>2);
    return size_t(h);
  }
};
struct ShortIndex {
  std::unordered_map<Clause,uint32_t,HashClause> freq;
  uint64_t eligible=0,duplicate=0;bool complete=true;
  explicit ShortIndex(const CNF&f) {
    for(uint32_t i=0;i<f.clauses.size();++i)if(!f.tautological[i]&&f.clauses[i].size()<=8)++eligible;
    if(eligible>INDEX_CAP){complete=false;return;}
    freq.reserve(size_t(eligible));
    for(uint32_t i=0;i<f.clauses.size();++i)if(!f.tautological[i]&&f.clauses[i].size()<=8) {
      uint32_t &n=freq[f.clauses[i]];duplicate+=n!=0;++n;
    }
  }
  bool has(const Clause&c)const{return freq.find(c)!=freq.end();}
};
bool taut_resolvent(const Clause&c,const Clause&d,uint32_t pivot) {
  for(Lit l:c)if(uint32_t(std::abs(l))!=pivot&&std::binary_search(d.begin(),d.end(),-l))return true;
  return false;
}
Block repetition(const CNF&f){return fraction("f_core_literal_repetition",f.repeated_literals,f.raw_literals,f.raw_literals);}
Block tautology(const CNF&f){return fraction("f_core_tautology",f.tautological_clauses,f.raw_clauses,f.raw_literals);}
Block duplicate(const CNF&,const ShortIndex&s) {
  if(!s.complete)return unavailable("f_core_duplicate_clause","CAPPED","more than1M eligible short clauses");
  return fraction("f_core_duplicate_clause",s.duplicate,s.eligible,s.eligible);
}
Block subsumption(const CNF&f,const ShortIndex&s) {
  const std::string key="f_core_subsumption";
  if(!s.complete)return unavailable(key,"CAPPED","short-clause index unavailable");
  uint64_t eligible=0,count=0,work=0;
  for(uint32_t cid=0;cid<f.clauses.size();++cid) {
    const Clause&c=f.clauses[cid];const size_t k=c.size();
    if(f.tautological[cid]||k<3||k>8)continue;
    ++eligible;bool witness=false;
    for(uint32_t mask=1;mask<(1U<<k)-1&&!witness;++mask) {
      if(__builtin_popcount(mask)<2)continue;
      if(++work>SUBSET_CAP)return unavailable(key,"CAPPED","2M strict subset probes",work);
      Clause d;for(size_t j=0;j<k;++j)if(mask&(1U<<j))d.push_back(c[j]);
      witness=s.has(d);
    }
    count+=witness;
  }
  return fraction(key,count,eligible,work);
}
Block self_subsumption(const CNF&f,const ShortIndex&s) {
  const std::string key="f_core_self_subsumption";
  if(!s.complete)return unavailable(key,"CAPPED","short-clause index unavailable");
  uint64_t eligible=0,count=0,work=0;
  for(uint32_t cid=0;cid<f.clauses.size();++cid) {
    const Clause&c=f.clauses[cid];if(f.tautological[cid]||c.size()!=4)continue;
    ++eligible;bool witness=false;
    for(size_t j=0;j<4&&!witness;++j) {
      if(++work>SUBSET_CAP)return unavailable(key,"CAPPED","2M width4 strengthening probes",work);
      Clause d=c;d[j]=-d[j];std::sort(d.begin(),d.end());witness=s.has(d);
    }
    count+=witness;
  }
  return fraction(key,count,eligible,work);
}
Block fanout(const CNF&f) {
  uint64_t numerator=0,denominator=0;
  for(uint32_t v=1;v<=f.n;++v){uint64_t p=f.pos[v].size(),n=f.neg[v].size();numerator+=p*n;denominator+=p+n;}
  return fraction("f_core_resolution_fanout",numerator,denominator,f.n);
}
Block resolvent_tautology(const CNF&f) {
  const std::string key="f_core_resolvent_tautology";uint64_t count=0,eligible=0;
  for(uint32_t v=1;v<=f.n;++v) {
    if(uint64_t(f.pos[v].size())*f.neg[v].size()>64)continue;
    for(uint32_t a:f.pos[v])for(uint32_t b:f.neg[v]) {
      const Clause&c=f.clauses[a];const Clause&d=f.clauses[b];
      if(c.size()<3||c.size()>8||d.size()<3||d.size()>8||std::max(c.size(),d.size())<4)continue;
      if(++eligible>PAIR_CAP)return unavailable(key,"CAPPED","200k complete eligible resolvent-pair cap",eligible);
      count+=taut_resolvent(c,d,v);
    }
  }
  return fraction(key,count,eligible,eligible);
}
Block blockedness(const CNF&f) {
  const std::string key="f_core_blocked_polarity";uint64_t eligible=0,work=0;int64_t count=0;
  for(uint32_t cid=0;cid<f.clauses.size();++cid) {
    const Clause&c=f.clauses[cid];if(f.tautological[cid]||c.empty()||c.size()>8)continue;
    bool admitted=true;
    for(Lit l:c) {
      const auto&op=occurrences(f,-l);
      if(op.size()>16){admitted=false;break;}
      for(uint32_t d:op)if(f.clauses[d].size()>8){admitted=false;break;}
      if(!admitted)break;
    }
    if(!admitted)continue;
    ++eligible;bool positive=false,negative=false;
    for(Lit l:c) {
      bool blocked=true;
      for(uint32_t did:occurrences(f,-l)) {
        if(++work>BCE_CAP)return unavailable(key,"CAPPED","2M exact blocking-pair checks",work);
        if(!taut_resolvent(c,f.clauses[did],uint32_t(std::abs(l)))){blocked=false;break;}
      }
      if(blocked){if(l>0)positive=true;else negative=true;}
    }
    count+=int(positive)-int(negative);
  }
  return fraction(key,count,eligible,work);
}
uint64_t signature(const CNF&f,uint32_t v) {
  uint64_t h=0x243f6a8885a308d3ULL;
  for(uint32_t c:f.pos[v])h^=c+0x9e3779b97f4a7c15ULL+(h<<6)+(h>>2);
  h^=0x13198a2e03707344ULL+f.pos[v].size();
  for(uint32_t c:f.neg[v])h^=c+0xa4093822299f31d0ULL+(h<<6)+(h>>2);
  return h^uint64_t(f.neg[v].size());
}
Block twins(const CNF&f) {
  const std::string key="f_core_variable_twins";
  if(f.active_variables>INDEX_CAP)return unavailable(key,"CAPPED","more than1M active-variable fingerprint entries");
  struct Group{uint32_t representative;uint64_t count;};
  std::unordered_map<uint64_t,std::vector<Group>> buckets;
  uint64_t work=0,count=0;
  for(uint32_t v=1;v<=f.n;++v)if(!f.pos[v].empty()||!f.neg[v].empty()) {
    auto&bucket=buckets[signature(f,v)];bool found=false;
    for(auto&g:bucket) {
      if(++work>TWIN_CAP)return unavailable(key,"CAPPED","2M exact twin-group comparisons",work);
      uint32_t u=g.representative;
      if(f.pos[v]==f.pos[u]&&f.neg[v]==f.neg[u]){++g.count;found=true;break;}
    }
    if(!found)bucket.push_back({v,1});
  }
  for(const auto&entry:buckets)for(const auto&g:entry.second)if(g.count>1)count+=g.count;
  return fraction(key,count,f.active_variables,work);
}
Block flip_gain(const CNF&f) {
  std::vector<uint8_t> assignment(f.n+1);
  std::vector<int64_t> gain(f.n+1,0);
  for(uint32_t v=1;v<=f.n;++v)assignment[v]=f.pos[v].size()>f.neg[v].size();
  uint64_t work=0;
  for(uint32_t cid=0;cid<f.clauses.size();++cid)if(!f.tautological[cid]) {
    const Clause&c=f.clauses[cid];uint32_t satisfied=0,sole=0;
    for(Lit l:c){++work;uint32_t v=uint32_t(std::abs(l));if(bool(assignment[v])==(l>0)){++satisfied;sole=v;}}
    if(!satisfied)for(Lit l:c)++gain[uint32_t(std::abs(l))];
    else if(satisfied==1)--gain[sole];
  }
  int64_t count=0;
  for(uint32_t v=1;v<=f.n;++v)if(gain[v]>0)count+=assignment[v]?-1:1;
  return fraction("f_core_majority_flip_gain",count,f.active_variables,work);
}
} // namespace

int main(int argc,char**argv) {
  try {
    std::string path,only;
    for(int i=1;i<argc;++i) {
      std::string a=argv[i];
      if(a=="--module"&&i+1<argc){if(std::string(argv[++i])!="core10")throw std::runtime_error("unknown module");}
      else if(a=="--block"&&i+1<argc)only=argv[++i];
      else if(path.empty())path=a;else throw std::runtime_error("extra arguments");
    }
    if(path.empty())throw std::runtime_error("usage: structural_core [--module core10] [--block NAME] INPUT.cnf");
    CNF f=read_cnf(path);double index_start=cpu_now();ShortIndex index(f);f.shared_index_cpu_s=cpu_now()-index_start;
    std::vector<Block> blocks;
    const std::vector<std::pair<std::string,std::function<Block()>>> functions={
      {"literal_repetition",[&]{return repetition(f);}}, {"tautology",[&]{return tautology(f);}},
      {"duplicate_clause",[&]{return duplicate(f,index);}}, {"subsumption",[&]{return subsumption(f,index);}},
      {"self_subsumption",[&]{return self_subsumption(f,index);}}, {"resolution_growth",[&]{return fanout(f);}},
      {"resolvent_tautology",[&]{return resolvent_tautology(f);}}, {"blockedness",[&]{return blockedness(f);}},
      {"variable_twins",[&]{return twins(f);}}, {"local_flip_gain",[&]{return flip_gain(f);}}};
    bool matched=only.empty();
    for(const auto&entry:functions)if(only.empty()||only==entry.first) {
      matched=true;double begin=cpu_now();Block b=entry.second();b.cpu_s=cpu_now()-begin;blocks.push_back(std::move(b));
    }
    if(!matched)throw std::runtime_error("unknown block");
    emit(f,blocks,"core10");return 0;
  } catch(const std::exception&e) {std::cerr<<"TA100 core: "<<e.what()<<'\n';return 2;}
}
