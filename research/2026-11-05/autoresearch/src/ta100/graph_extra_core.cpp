#include "graph_extra_features.hpp"
int main(int argc,char**argv) {
 try {
  if(argc!=4||std::string(argv[1])!="--module") throw std::runtime_error("usage: graph_extra_core --module MODULE INPUT.cnf");
  const std::string module=argv[2];
  if(module!="graph20"&&module!="graph30"&&module!="graph40"&&module!="graph_all30") throw std::runtime_error("unknown module");
  auto f=ta100::read_cnf(argv[3]);
  const double end=ta100::cpu_now()+std::max(0.0,4.3-f.parse_cpu_s);
  std::vector<ta100::Block> blocks;
  const std::vector<std::string> order=module=="graph_all30"?std::vector<std::string>{"graph40","graph30","graph20"}:std::vector<std::string>{module};
  for(const auto &part:order) {
   const double remaining=end-ta100::cpu_now();
   if(remaining<=0.03) {
    if(part=="graph20") for(const auto &key:std::vector<std::string>{"graph_modularity","graph_box_scaling","graph_k33_witness","graph_elimination_width","graph_percolation","graph_betweenness","graph_harmonic_access","graph_detour","graph_nonbacktracking","graph_gyo"}) blocks.push_back(ta100::unavailable(key,"RESOURCE_LIMIT","shared module CPU allowance exhausted"));
    if(part=="graph30") for(const auto &key:std::vector<std::string>{"graph_laminarity","graph_shattering","graph_cutrank","graph_chordality","graph_hyperbolicity","graph_majority_gate_coverage","graph_reconvergence","graph_gate_output_direction","graph_gate_ambiguity","graph_gate_congruence"}) blocks.push_back(ta100::unavailable(key,"RESOURCE_LIMIT","shared module CPU allowance exhausted"));
    if(part=="graph40") for(const auto &key:std::vector<std::string>{"graph_controllability","graph_observability","graph_binate_cones","graph_other_functional","graph_canalizing_depth","graph_anf_degree","graph_sign_bundling","graph_community_polarity","graph_transport_curvature","graph_betti1"}) blocks.push_back(ta100::unavailable(key,"RESOURCE_LIMIT","shared module CPU allowance exhausted"));
    continue;
   }
   std::vector<ta100::Block> v;
   if(part=="graph40") v=ta100_graph::graph40(f,remaining);
   else if(part=="graph30") v=ta100_graph::graph30(f,remaining);
   else v=ta100_graph::graph20(f,remaining);
   blocks.insert(blocks.end(),v.begin(),v.end());
  }
  ta100::emit(f,blocks,module); return 0;
 } catch(const std::exception&e) {std::cerr<<e.what()<<'\n';return 2;}
}
