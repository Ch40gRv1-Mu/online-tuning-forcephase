// Combined original structural features plus explicitly defined depth proxies.
// No solver outcomes, file names, family labels or variable IDs are emitted.
#define main original_structure_main
#include "cnf_structure.cpp"
#undef main
#include <utility>

struct DepthFeatures : Features {
  std::vector<std::pair<U,U>> incidence_edges;
  std::vector<U> geometry_stamp;
  bool geometry_exact=true;
  void init(U n) { Features::init(n); geometry_stamp.resize(n+1); }
  void add(const std::vector<int>& c) {
    Features::add(c);
    if(!geometry_exact)return;
    for(int l:c) {
      U v=std::abs(l);
      if(geometry_stamp[v]==clauses)continue;
      geometry_stamp[v]=U(clauses);
      if(incidence_edges.size()>=20000000) {
        geometry_exact=false;
        std::vector<std::pair<U,U>>().swap(incidence_edges);break;
      }
      incidence_edges.emplace_back(v-1,U(clauses-1));
    }
  }
  std::vector<double> peel() {
    if(!geometry_exact || uint64_t(declared)+clauses>10000000)
      return {NAN,NAN,NAN,0};
    U N=declared+U(clauses);
    std::vector<U> deg(N),off(N+1),layer(N),queue;
    for(auto e:incidence_edges) {++deg[e.first];++deg[declared+e.second];}
    for(U v=0;v<N;++v)off[v+1]=off[v]+deg[v];
    std::vector<U> adj(off.back()),cursor=off;
    for(auto e:incidence_edges) {
      U a=e.first,b=declared+e.second;adj[cursor[a]++]=b;adj[cursor[b]++]=a;
    }
    std::vector<std::pair<U,U>>().swap(incidence_edges);
    std::vector<U>().swap(cursor);
    std::vector<uint8_t> removed(N);
    for(U v=0;v<N;++v)if((v>=declared || deg[v]) && deg[v]<=1) {
      layer[v]=1;queue.push_back(v);
    }
    U depth=0;
    for(size_t p=0;p<queue.size();++p) {
      U v=queue[p];if(removed[v])continue;
      removed[v]=1;depth=std::max(depth,layer[v]);
      for(U k=off[v];k<off[v+1];++k) {
        U w=adj[k];if(removed[w])continue;
        if(deg[w])--deg[w];
        if(deg[w]==1 && !layer[w]) {layer[w]=layer[v]+1;queue.push_back(w);}
      }
    }
    uint64_t core=0,twice_edges=0;
    for(U v=0;v<N;++v)if((v>=declared || off[v+1]>off[v]) && !removed[v]) {
      ++core;twice_edges+=deg[v];
    }
    return {double(depth),double(core)/std::max<uint64_t>(1,active+clauses),
            double(twice_edges)/2/std::max<uint64_t>(1,incidences),1};
  }
  std::vector<double> gates_depth() {
    if(!motifs_exact)return {NAN,NAN,NAN,NAN,0};
    std::vector<std::pair<U,U>> edges;
    uint64_t count=0,positive_outputs=0;
    std::vector<uint8_t> has(declared+1);
    for(auto c:ternaries)for(int i=0;i<3;++i) {
      if(!binaries.count(pair_key(c[i]^1,c[(i+1)%3]^1)) ||
         !binaries.count(pair_key(c[i]^1,c[(i+2)%3]^1)))continue;
      if(edges.size()>=4000000)return {NAN,NAN,NAN,NAN,0};
      U out=c[i]>>1,a=c[(i+1)%3]>>1,b=c[(i+2)%3]>>1;
      edges.emplace_back(a,out);edges.emplace_back(b,out);
      has[a]=has[b]=has[out]=1;++count;positive_outputs+=!(c[i]&1);
    }
    if(edges.empty())return {NAN,NAN,0,NAN,1};
    uint64_t nodes=std::accumulate(has.begin(),has.end(),uint64_t(0));
    std::vector<std::vector<U>> g(declared+1),rev(declared+1);
    for(auto e:edges) {g[e.first].push_back(e.second);rev[e.second].push_back(e.first);}
    std::vector<uint8_t> seen(declared+1);
    std::vector<U> order;
    std::vector<std::pair<U,U>> stack;
    for(U s=1;s<=declared;++s)if(has[s]&&!seen[s]) {
      seen[s]=1;stack.emplace_back(s,0);
      while(!stack.empty()) {
        U v=stack.back().first;U &i=stack.back().second;
        if(i<g[v].size()) {U w=g[v][i++];if(!seen[w]) {seen[w]=1;stack.emplace_back(w,0);}}
        else {order.push_back(v);stack.pop_back();}
      }
    }
    std::vector<U> component(declared+1,UINT32_MAX),sizes,work;
    for(auto it=order.rbegin();it!=order.rend();++it)if(component[*it]==UINT32_MAX) {
      U id=U(sizes.size()),size=0;work.push_back(*it);component[*it]=id;
      while(!work.empty()) {
        U v=work.back();work.pop_back();++size;
        for(U w:rev[v])if(component[w]==UINT32_MAX) {component[w]=id;work.push_back(w);}
      }
      sizes.push_back(size);
    }
    std::vector<std::vector<U>>().swap(g);std::vector<std::vector<U>>().swap(rev);
    U K=U(sizes.size());std::vector<std::vector<U>> dag(K);std::vector<U> indeg(K),depth(K),q;
    for(auto e:edges) {
      U a=component[e.first],b=component[e.second];if(a==b)continue;
      dag[a].push_back(b);++indeg[b];
    }
    for(U i=0;i<K;++i)if(!indeg[i])q.push_back(i);
    U maximum=0;
    for(size_t i=0;i<q.size();++i) {
      U v=q[i];maximum=std::max(maximum,depth[v]);
      for(U w:dag[v]) {depth[w]=std::max(depth[w],depth[v]+1);if(!--indeg[w])q.push_back(w);}
    }
    if(q.size()!=K)throw std::runtime_error("condensation must be acyclic");
    uint64_t cyclic=0;for(U size:sizes)if(size>1)cyclic+=size;
    return {double(maximum),double(cyclic)/nodes,double(nodes)/std::max<uint64_t>(1,active),
            double(positive_outputs)/count,1};
  }
  void combined(double elapsed,const std::vector<double>& a,const std::vector<double>& b) {
    std::ostringstream original;auto previous=std::cout.rdbuf(original.rdbuf());
    Features::print(elapsed);std::cout.rdbuf(previous);
    auto value=original.str();auto close=value.rfind('}');
    std::cout<<value.substr(0,close)<<std::setprecision(12);
    const char* names[]={"d_leaf_peeling_rounds","d_core_vertex_fraction","d_core_edge_fraction",
      "d_incidence_geometry_exact","d_gate_condensation_depth","d_gate_cyclic_variable_fraction",
      "d_gate_variable_coverage","d_gate_output_positive_fraction","d_gate_depth_exact"};
    std::vector<double> vals=a;vals.insert(vals.end(),b.begin(),b.end());
    for(size_t i=0;i<vals.size();++i) {
      std::cout<<",\""<<names[i]<<"\":";
      if(std::isfinite(vals[i]))std::cout<<vals[i];else std::cout<<"null";
    }
    std::cout<<"}\n";
  }
};

int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("usage: cnf_depth INPUT.cnf");
    auto start=std::chrono::steady_clock::now();std::ifstream input(argv[1]);
    if(!input)throw std::runtime_error("cannot open input");
    DepthFeatures f;bool header=false;std::vector<int> clause;std::string line;
    while(std::getline(input,line)) {
      const char* p=line.c_str();while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;
      if(!*p||*p=='c')continue;
      if(*p=='p') {
        if(header)throw std::runtime_error("duplicate header");
        std::istringstream h(p);std::string marker,format;uint64_t n,m;
        if(!(h>>marker>>format>>n>>m)||format!="cnf"||n>5000000)throw std::runtime_error("invalid header");
        f.init(U(n));f.declared_clauses=m;header=true;continue;
      }
      if(!header)throw std::runtime_error("missing header");
      while(*p) {
        while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;if(!*p)break;
        char* end=nullptr;long lit=std::strtol(p,&end,10);
        if(end==p||lit>5000000||lit< -5000000)throw std::runtime_error("invalid literal");
        p=end;if(lit)clause.push_back(int(lit));else {f.add(clause);clause.clear();}
      }
    }
    if(!header||!clause.empty()||f.clauses!=f.declared_clauses)throw std::runtime_error("incomplete CNF");
    auto a=f.peel();auto b=f.gates_depth();
    f.combined(std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count(),a,b);
    return 0;
  }catch(const std::exception& e){std::cerr<<"depth feature error: "<<e.what()<<"\n";return 2;}
}
