// Exact legacy linear42 statistics in one pass; no unused graph fields or SAT.
#include <algorithm>
#include <array>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <unistd.h>
#include <vector>

#include "src/util/StreamBuffer.h"
#include "src/util/CaptureDistribution.h"

int main(int argc, char **argv) {
    if (argc != 2) return 64;
    rlimit core{0,0}, cpu{8,8};
    setrlimit(RLIMIT_CORE,&core);
    if (setrlimit(RLIMIT_CPU,&cpu)) return 70;
    alarm(12);
    auto started=std::clock();
    try {
        StreamBuffer input(argv[1]);
        std::vector<unsigned> positive_degree(1),negative_degree(1),horn_degree(1),invhorn_degree(1);
        std::vector<double> clause_balance,variable_balance;
        std::array<unsigned,11> sizes{};
        unsigned variables=0,clauses=0,horn=0,invhorn=0,positive=0,negative=0;
        Cl clause;
        while (input.readClause(clause)) {
            if (clause.empty()) throw std::runtime_error("upstream empty-clause feature path unsupported");
            unsigned neg=0;
            for (auto lit:clause) {
                unsigned v=lit.var();
                if (v>5000000) throw std::runtime_error("feature variable allocation limit");
                if (v>variables) {
                    variables=v;
                    positive_degree.resize(v+1);negative_degree.resize(v+1);
                    horn_degree.resize(v+1);invhorn_degree.resize(v+1);
                }
                if (lit.sign()) {++negative_degree[v];++neg;}
                else ++positive_degree[v];
            }
            unsigned pos=clause.size()-neg;
            ++clauses;++sizes[std::min(clause.size(),size_t(10))];
            if (pos<=1) {
                ++horn;if (!pos) ++negative;
                for (auto lit:clause) ++horn_degree[lit.var()];
            }
            if (neg<=1) {
                ++invhorn;if (!neg) ++positive;
                for (auto lit:clause) ++invhorn_degree[lit.var()];
            }
            clause_balance.push_back(double(std::min(pos,neg))/std::max(pos,neg));
        }
        if (!variables || !clauses) throw std::runtime_error("undefined trained statistics for empty input");
        // Preserve upstream's v<n_vars boundary, including omission of the last variable.
        for (unsigned v=0;v<variables;++v) {
            double p=positive_degree[v],n=negative_degree[v];
            if (std::max(p,n)>0) variable_balance.push_back(std::min(p,n)/std::max(p,n));
        }
        std::vector<unsigned> degree(variables);
        for (unsigned v=1;v<=variables;++v) degree[v-1]=positive_degree[v]+negative_degree[v];
        // Upstream swaps away dummy0 before sorting. Erasing it yields the identical multiset.
        horn_degree.erase(horn_degree.begin());invhorn_degree.erase(invhorn_degree.begin());
        std::map<std::string,double> f{{"variables",variables},{"clauses",clauses},
            {"horn",horn},{"invhorn",invhorn},{"positive",positive},{"negative",negative}};
        for (unsigned k=1;k<10;++k) f["cls"+std::to_string(k)]=sizes[k];
        f["cls10p"]=sizes[10];
        const std::array<std::string,5> names{"mean","variance","min","max","entropy"};
        auto add=[&](std::string prefix,const std::vector<double>& values) {
            for (unsigned j=0;j<5;++j) f[prefix+"_"+names[j]]=values[j];
        };
        // Reuse the exact pinned sorted-statistic/legacy entropy implementation.
        add("balancecls",getDistributionStats(clause_balance));
        add("balancevars",getDistributionStats(variable_balance));
        add("hornvars",getDistributionStats(horn_degree));
        add("invhornvars",getDistributionStats(invhorn_degree));
        add("vcg_vdegree",getDistributionStats(degree));
        std::cout<<std::setprecision(17)<<"{\"features\":{";
        bool first=true;
        for (auto item:f) {
            if (!std::isfinite(item.second)) throw std::runtime_error("nonfinite upstream feature");
            if (!first) std::cout<<',';
            first=false;std::cout<<'\"'<<item.first<<"\":"<<item.second;
        }
        std::cout<<"},\"inner_CPU_s\":"<<double(std::clock()-started)/CLOCKS_PER_SEC
                 <<",\"schema\":\"linear42.rawstats.v1\"}\n";
    } catch (const std::exception& exc) {
        std::cerr<<exc.what()<<'\n';return 65;
    }
    return 0;
}
