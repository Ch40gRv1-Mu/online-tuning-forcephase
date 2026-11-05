#pragma once
// Input-only TA100 graph mechanism block. No solver, labels, IDs or role access.
#include "cnf_data.hpp"
#include <array>
#include <deque>
#include <map>
#include <numeric>
#include <queue>
#include <set>
#include <unordered_map>
#include <unordered_set>
namespace ta100_graph {
using U=uint32_t; using Q=uint64_t;
struct Budget { double end; explicit Budget(double seconds):end(ta100::cpu_now()+seconds){} bool done()const{return ta100::cpu_now()>end;} };
inline Q mix(Q x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
inline Q pairkey(U a,U b){if(a>b)std::swap(a,b);return(Q(a)<<32)|b;}
inline U code(int32_t l){return U(2*std::abs(l)+(l<0));}
inline ta100::Block numeric(std::string key,double value,Q work=0){ta100::Block b;b.key=std::move(key);b.value=value;b.work=work;if(!std::isfinite(value))b.status="UNDEFINED",b.reason="zero variance or eligible denominator";return b;}
inline ta100::Block limited(std::string key,const std::string&why,Q work=0){return ta100::unavailable(std::move(key),"RESOURCE_LIMIT",why,work);}
struct CSR {U N=0;Q E=0;std::vector<Q> off;std::vector<U> adj,deg;};
inline CSR incidence(const ta100::CNF&f){CSR g;g.N=f.n+U(f.clauses.size());g.deg.assign(g.N,0);g.off.assign(Q(g.N)+1,0);
 for(U c=0;c<f.clauses.size();++c)if(!f.tautological[c])for(auto l:f.clauses[c]){++g.deg[U(std::abs(l))-1];++g.deg[f.n+c];++g.E;}
 for(U i=0;i<g.N;++i)g.off[i+1]=g.off[i]+g.deg[i];g.adj.resize(g.off.back());auto at=g.off;
 for(U c=0;c<f.clauses.size();++c)if(!f.tautological[c])for(auto l:f.clauses[c]){U v=U(std::abs(l))-1,w=f.n+c;g.adj[at[v]++]=w;g.adj[at[w]++]=v;}return g;}
struct Gate {int32_t z=0,a=0,b=0;bool ambiguous=false;};
inline bool samegate(const Gate&a,const Gate&b){return a.z==b.z&&a.a==b.a&&a.b==b.b;}
struct GateData {std::map<U,Gate> gates;std::set<ta100::Clause> pool;Q matches=0,ambiguous=0;bool complete=false;};
inline GateData gates(const ta100::CNF&f,Budget&budget){GateData data;std::unordered_set<Q> bin;Q work=0;
 for(U c=0;c<f.clauses.size();++c)if(!f.tautological[c]&&f.clauses[c].size()==2){auto&a=f.clauses[c];bin.insert(pairkey(code(a[0]),code(a[1])));if(bin.size()>1000000||(++work%8192==0&&budget.done()))return data;}
 for(U c=0;c<f.clauses.size();++c)if(!f.tautological[c]&&f.clauses[c].size()==3){const auto&a=f.clauses[c];for(U j=0;j<3;++j){int32_t z=a[j],x=-a[(j+1)%3],y=-a[(j+2)%3];if(x>y)std::swap(x,y);
   if(bin.count(pairkey(code(-z),code(x)))&&bin.count(pairkey(code(-z),code(y)))){Gate g{z,x,y,false};U v=std::abs(z);auto it=data.gates.find(v);if(it==data.gates.end())data.gates[v]=g;else if(!samegate(it->second,g))it->second.ambiguous=true;++data.matches;}}
   if(++work%8192==0&&budget.done())return data;}
 for(auto&item:data.gates){auto&g=item.second;if(g.ambiguous){++data.ambiguous;continue;}for(auto clause:std::vector<ta100::Clause>{{-g.z,g.a},{-g.z,g.b},{g.z,-g.a,-g.b}}){std::sort(clause.begin(),clause.end());data.pool.insert(std::move(clause));}}
 data.complete=true;return data;}
inline std::vector<ta100::Block> compute(const ta100::CNF&f,double cpu_budget=4.2){Budget budget(cpu_budget);std::vector<ta100::Block> out;const double total_start=ta100::cpu_now();
 auto run=[&](const std::string&key,auto operation){double t=ta100::cpu_now();ta100::Block b=budget.done()?limited(key,"module CPU budget exhausted before block"):operation();b.cpu_s=ta100::cpu_now()-t;out.push_back(std::move(b));};
 const U n=f.n,m=U(f.clauses.size());std::vector<U> degree(n+1),horn(n+1);std::array<std::array<Q,9>,2> table{};Q L=0;long double sx=0,sy=0,sxx=0,syy=0,sxy=0;
 for(U v=1;v<=n;++v)degree[v]=U(f.pos[v].size()+f.neg[v].size());
 for(U c=0;c<m;++c)if(!f.tautological[c]){const auto&a=f.clauses[c];U k=U(a.size()),np=0;for(auto l:a)np+=l>0;for(auto l:a){U d=degree[std::abs(l)];++L;sx+=d;sy+=k;sxx+=Q(d)*d;syy+=Q(k)*k;sxy+=Q(d)*k;if(np<=1)++horn[std::abs(l)];++table[l<0][std::min<U>(k,9)-1];}}
 double vx=double(L*sxx-sx*sx),vy=double(L*syy-sy*sy);out.push_back(numeric("graph_incidence_assortativity",vx>0&&vy>0?double(L*sxy-sx*sy)/std::sqrt(vx*vy):NAN,L));
 long double information=0,H=0;Q sign[2]={0,0},arity[9]={};for(U s=0;s<2;++s)for(U k=0;k<9;++k)sign[s]+=table[s][k],arity[k]+=table[s][k];
 if(L)for(U s=0;s<2;++s)if(sign[s]){long double p=static_cast<long double>(sign[s])/L;H-=p*std::log(p);for(U k=0;k<9;++k)if(table[s][k]){p=static_cast<long double>(table[s][k])/L;information+=p*std::log(static_cast<long double>(table[s][k])*L/(static_cast<long double>(sign[s])*arity[k]));}}
 out.push_back(numeric("graph_sign_arity_information",H>0?double(information/H):NAN,L));Q iface=0;for(U v=1;v<=n;++v)iface+=std::min(horn[v],degree[v]-horn[v]);out.push_back(ta100::fraction("graph_horn_interface",iface,L,L));
 // CSR is shared setup; charge it explicitly to the next block, never free.
 double csr_start=ta100::cpu_now();CSR g;if(!budget.done())g=incidence(f);double csr_cpu=ta100::cpu_now()-csr_start;
 run("graph_core_retention",[&](){auto d=g.deg;std::deque<U> queue;std::vector<uint8_t> removed(g.N);for(U u=0;u<g.N;++u)if(d[u]<2)queue.push_back(u);Q work=0;
  while(!queue.empty()){U u=queue.front();queue.pop_front();if(removed[u])continue;removed[u]=1;for(Q j=g.off[u];j<g.off[u+1];++j){U v=g.adj[j];if(!removed[v]&&d[v]&&--d[v]==1)queue.push_back(v);}if(++work%8192==0&&budget.done())return limited("graph_core_retention","peeling budget",work);}
  Q retained=0;for(U u=0;u<n;++u)retained+=g.deg[u]>0&&!removed[u];return ta100::fraction("graph_core_retention",retained,f.active_variables,work);});out.back().cpu_s+=csr_cpu;
 run("graph_articulation_fragility",[&](){std::vector<U> disc(g.N),low(g.N),parent(g.N,UINT32_MAX);std::vector<Q> cursor=g.off,weight(g.N),sep(g.N);std::vector<long double> sep2(g.N);U clock=0;Q work=0;long double best=0;
  for(U root=0;root<g.N;++root)if(g.deg[root]&&!disc[root]){std::vector<U> stack{root},members;disc[root]=low[root]=++clock;weight[root]=root<n;
   while(!stack.empty()){U u=stack.back();if(cursor[u]<g.off[u+1]){U v=g.adj[cursor[u]++];if(v==parent[u])continue;if(!disc[v]){parent[v]=u;disc[v]=low[v]=++clock;weight[v]=v<n;stack.push_back(v);}else low[u]=std::min(low[u],disc[v]);}
    else {stack.pop_back();members.push_back(u);if(parent[u]!=UINT32_MAX){U p=parent[u];weight[p]+=weight[u];low[p]=std::min(low[p],low[u]);if(low[u]>=disc[p]){sep[p]+=weight[u];sep2[p]+=static_cast<long double>(weight[u])*weight[u];}}}
    if(++work%8192==0&&budget.done())return limited("graph_articulation_fragility","undirected DFS budget",work);}
   Q total=weight[root];for(U u:members)if(u<n&&total>1){Q rem=total-1-sep[u];long double separated=static_cast<long double>(total-1)*(total-1)-sep2[u]-static_cast<long double>(rem)*rem;best=std::max(best,separated);}}
  return numeric("graph_articulation_fragility",f.active_variables?double(best/(static_cast<long double>(f.active_variables)*f.active_variables)):NAN,work);});
 std::unordered_map<Q,U> pairs;bool pair_exact=true;Q visits=0;long double butterflies=0;
 run("graph_butterfly_overlap",[&](){for(U c=0;c<m;++c)if(!f.tautological[c]){const auto&a=f.clauses[c];for(U i=0;i<a.size();++i)for(U j=i+1;j<a.size();++j){if(++visits>2000000||pairs.size()>1000000||(visits%8192==0&&budget.done())){pair_exact=false;return limited("graph_butterfly_overlap","pair-enumeration cap",visits);}Q key=pairkey(std::abs(a[i]),std::abs(a[j]));auto&count=pairs[key];butterflies+=count++;}}
  return numeric("graph_butterfly_overlap",visits?double(butterflies/visits):NAN,visits);});
 run("graph_primal_transitivity",[&](){if(!pair_exact)return limited("graph_primal_transitivity","primal pair index incomplete",visits);if(f.active_variables>200000)return limited("graph_primal_transitivity","primal vertex cap");std::vector<std::vector<U>> adj(n+1);for(const auto&p:pairs){U a=U(p.first>>32),b=U(p.first);adj[a].push_back(b);adj[b].push_back(a);}for(auto&a:adj)std::sort(a.begin(),a.end());Q wedges=0,tri=0,work=0;for(U u=1;u<=n;++u){wedges+=Q(adj[u].size())*(adj[u].size()-1)/2;for(U v:adj[u])if(v>u){auto i=std::upper_bound(adj[u].begin(),adj[u].end(),v),j=std::upper_bound(adj[v].begin(),adj[v].end(),v);while(i!=adj[u].end()&&j!=adj[v].end()){if(++work>4000000||(work%8192==0&&budget.done()))return limited("graph_primal_transitivity","triangle intersection cap",work);if(*i==*j)++tri,++i,++j;else if(*i<*j)++i;else ++j;}}}return ta100::fraction("graph_primal_transitivity",3*int64_t(tri),wedges,work);});
 double gate_start=ta100::cpu_now();GateData gate;if(!budget.done())gate=gates(f,budget);double gate_cpu=ta100::cpu_now()-gate_start;
 run("graph_gate_sharing",[&](){if(!gate.complete)return limited("graph_gate_sharing","gate recognition cap/budget");std::vector<U> fanout(n+1);Q inputs=0;for(const auto&item:gate.gates)if(!item.second.ambiguous){++fanout[std::abs(item.second.a)];++fanout[std::abs(item.second.b)];inputs+=2;}Q sharing=0;for(U v=1;v<=n;++v)if(fanout[v])sharing+=fanout[v]-1;return ta100::fraction("graph_gate_sharing",sharing,inputs,gate.matches);});out.back().cpu_s+=gate_cpu;
 run("graph_circuit_residual_interface",[&](){if(!gate.complete)return limited("graph_circuit_residual_interface","gate recognition incomplete");std::vector<uint8_t> output(n+1);for(const auto&item:gate.gates)if(!item.second.ambiguous)output[item.first]=1;Q total=0,residual=0;for(U c=0;c<m;++c)if(!f.tautological[c]){bool internal=gate.pool.count(f.clauses[c]);for(auto l:f.clauses[c])if(output[std::abs(l)]){++total;residual+=!internal;}}return ta100::fraction("graph_circuit_residual_interface",residual,total,L);});
 run("graph_diffusion_return",[&](){Q active=0;for(auto d:g.deg)active+=d>0;if(!active)return numeric("graph_diffusion_return",NAN);std::vector<double> x(g.N),y(g.N),z(g.N);long double trace=0;Q work=0;
  for(U seed=0;seed<8;++seed){for(U u=0;u<g.N;++u)x[u]=z[u]=g.deg[u]?((mix(Q(u)+Q(seed)*g.N)&1)?1.:-1.):0.;for(U step=0;step<4;++step){std::fill(y.begin(),y.end(),0);for(U u=0;u<g.N;++u)if(g.deg[u]){double sum=0;for(Q j=g.off[u];j<g.off[u+1];++j){U v=g.adj[j];sum+=x[v]/std::sqrt(double(g.deg[v]));}y[u]=sum/std::sqrt(double(g.deg[u]));if(++work%4096==0&&budget.done())return limited("graph_diffusion_return","fixed-probe sparse-walk budget",work);}x.swap(y);}for(U u=0;u<g.N;++u)trace+=z[u]*x[u];}
  return numeric("graph_diffusion_return",double(trace/(8*active)),work);});
 // Setup for the first three stream descriptors is measured once on S01.
 double accounted=0;for(const auto&b:out)accounted+=b.cpu_s;out[0].cpu_s+=std::max(0.,ta100::cpu_now()-total_start-accounted);
 return out;}
} // namespace ta100_graph
