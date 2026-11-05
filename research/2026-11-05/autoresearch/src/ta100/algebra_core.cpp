#include "algebra_features.hpp"
#include "core_extra_features.hpp"
int main(int argc,char**argv){try{
 if(argc!=4||std::string(argv[1])!="--module")throw std::runtime_error("usage: algebra_core --module algebra10/algebra8/algebra18/algebra20 INPUT.cnf");
 std::string group=argv[2];if(group!="algebra10"&&group!="algebra8"&&group!="algebra18"&&group!="algebra20")throw std::runtime_error("unknown algebra group");
 auto f=ta100::read_cnf(argv[3]);double allowance=std::max(0.,4.3-f.parse_cpu_s),started=ta100::cpu_now();std::vector<ta100::Block>extras;
 // Freeze the two cheap node-owned mechanisms first, then the ROOT18, under
 // one total CPU budget and one parse. Output order remains ROOT18 then extras.
 if(group=="algebra20")extras=ta100_core_extra::compute(f,std::min(.5,allowance));
 double remaining=std::max(0.,allowance-(ta100::cpu_now()-started));
 auto blocks=ta100_algebra::compute_selected(f,remaining,group!="algebra8",group!="algebra10");
 blocks.insert(blocks.end(),extras.begin(),extras.end());ta100::emit(f,blocks,group);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
