"""Exact existing top10 policy trees. Features must use original extractor definitions.
Acquisition is external; no claim of end-to-end benefit. Rank includes old static.
"""
import json
import math

POLICIES = json.loads(r'''
[
  {
    "rank": 1,
    "representative_round": "I001",
    "members": [
      "I001"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_positive_fraction",
        "left": {
          "feature": "s_positive_fraction",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.196010372787
        },
        "right": {
          "feature": "td_chrono_share",
          "left": {
            "action": "false"
          },
          "right": {
            "action": "true"
          },
          "threshold": 0.226738
        },
        "threshold": 0.388031304508
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": 0.0016006724978476772,
    "gain_vs_fixed_true": 0.05439238790894785,
    "exploratory_interval95_vs_old_static": [
      -0.0016853268262476573,
      0.006909699376192766
    ],
    "result_path": "outputs/ta100/B01/I001/result.json",
    "result_sha256": "5559f0925e4b786c570fa5f2f9a4268437acc84debc7650cb97d379d3e2810f5",
    "fit_group_cv_gain": -0.0063470545757631225
  },
  {
    "rank": 2,
    "representative_round": "I002",
    "members": [
      "I002",
      "I004",
      "I005",
      "I006",
      "I007",
      "I008",
      "I009",
      "I010",
      "I011",
      "I012",
      "I013",
      "I014",
      "I015",
      "I016",
      "I017",
      "I018",
      "I019",
      "I020",
      "I021",
      "I022",
      "I023",
      "I024",
      "I025",
      "I026",
      "I028",
      "I029",
      "I030",
      "I031",
      "I032",
      "I033",
      "I034",
      "I035",
      "I036",
      "I037",
      "I038",
      "I039",
      "I040",
      "I041",
      "I042",
      "I043",
      "I044",
      "I045",
      "I046",
      "I047",
      "I048",
      "I049",
      "I050",
      "I051",
      "I052",
      "I053",
      "I054",
      "I056",
      "I057",
      "I058",
      "I060",
      "I061",
      "I062",
      "I063",
      "I064",
      "I065",
      "I067",
      "I068",
      "I070",
      "I071",
      "I072",
      "I073",
      "I074",
      "I075",
      "I076",
      "I077",
      "I078",
      "I079",
      "I080",
      "I081",
      "I082",
      "I083",
      "I084",
      "I085",
      "I086",
      "I087",
      "I089",
      "I090",
      "I091",
      "I092",
      "I093",
      "I094",
      "I097",
      "I100"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_positive_fraction",
        "left": {
          "feature": "s_positive_fraction",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.196010372787
        },
        "right": {
          "feature": "s_length_std",
          "left": {
            "action": "false"
          },
          "right": {
            "action": "true"
          },
          "threshold": 0.46287575042025
        },
        "threshold": 0.388031304508
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": 0.0,
    "gain_vs_fixed_true": 0.05287635313535044,
    "exploratory_interval95_vs_old_static": [
      0.0,
      0.0
    ],
    "result_path": "outputs/ta100/B01/I002/result.json",
    "result_sha256": "d3f28cbad7ca0f7c5f477665655779077862841f0a9fe7366df0b84594e5acfa",
    "fit_group_cv_gain": 0.0
  },
  {
    "rank": 3,
    "representative_round": "I027",
    "members": [
      "I027"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "g_cycle_excess_per_incidence",
        "left": {
          "feature": "g_cycle_excess_per_incidence",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.448787720882375
        },
        "right": {
          "feature": "graph_diffusion_return",
          "left": {
            "action": "false"
          },
          "right": {
            "action": "true"
          },
          "threshold": 0.00514181419561497
        },
        "threshold": 0.48654943603899997
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.0006476847269609731,
    "gain_vs_fixed_true": 0.05226291561473273,
    "exploratory_interval95_vs_old_static": [
      -0.012786492219778595,
      0.010291881596772372
    ],
    "result_path": "outputs/ta100/B03/I027/result.json",
    "result_sha256": "a6d717ced301ad8b7424f617c46c8c7662fc61bf01c1007db99b84f75fee43dd",
    "fit_group_cv_gain": -0.002388074531058937
  },
  {
    "rank": 4,
    "representative_round": "I069",
    "members": [
      "I069"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_positive_fraction",
        "left": {
          "feature": "s_positive_fraction",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.196010372787
        },
        "right": {
          "feature": "algebra_convex_fractional_pressure",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": -0.010195831732056088
        },
        "threshold": 0.388031304508
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.016824303383519812,
    "gain_vs_fixed_true": 0.03694165755879397,
    "exploratory_interval95_vs_old_static": [
      -0.07726058778240212,
      0.014287659762392569
    ],
    "result_path": "outputs/ta100/B07/I069/result.json",
    "result_sha256": "5f94a8dd5e5bfa7b0521529c13e5c3af8b9db97b7bbcaa7b697ae01be04ff5c0",
    "fit_group_cv_gain": 0.007280599971633328
  },
  {
    "rank": 5,
    "representative_round": "I098",
    "members": [
      "I098"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_positive_fraction",
        "left": {
          "feature": "s_positive_fraction",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.196010372787
        },
        "right": {
          "feature": "td_conflict_burstiness",
          "left": {
            "action": "false"
          },
          "right": {
            "action": "true"
          },
          "threshold": 2.8081808542
        },
        "threshold": 0.388031304508
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.017321616817607133,
    "gain_vs_fixed_true": 0.036470640245466424,
    "exploratory_interval95_vs_old_static": [
      -0.07811300954617811,
      0.01389039687097692
    ],
    "result_path": "outputs/ta100/B10/I098/result.json",
    "result_sha256": "73d1f8528b987b5517b687812e54f1bbdcede137e0f5accaddf0053f970c1894",
    "fit_group_cv_gain": -0.006931933358465203
  },
  {
    "rank": 6,
    "representative_round": "I059",
    "members": [
      "I059"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_positive_fraction",
        "left": {
          "feature": "s_positive_fraction",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.196010372787
        },
        "right": {
          "feature": "graph_nonbacktracking",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 3.9407252165999047
        },
        "threshold": 0.388031304508
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.018830666388464534,
    "gain_vs_fixed_true": 0.035041383712616336,
    "exploratory_interval95_vs_old_static": [
      -0.07860169049574219,
      0.011471510970840778
    ],
    "result_path": "outputs/ta100/B06/I059/result.json",
    "result_sha256": "0637cb846d7d3fbdabffdb76f12ece13da626e7204a895b63ae41adff8c557c4",
    "fit_group_cv_gain": 0.005520658647760968
  },
  {
    "rank": 7,
    "representative_round": "I095",
    "members": [
      "I095"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_positive_fraction",
        "left": {
          "feature": "s_positive_fraction",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.196010372787
        },
        "right": {
          "feature": "td_blocker_success_share",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.6019017555777499
        },
        "threshold": 0.388031304508
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.02101699232153531,
    "gain_vs_fixed_true": 0.0329706627216515,
    "exploratory_interval95_vs_old_static": [
      -0.08156324289958104,
      0.005745851451758794
    ],
    "result_path": "outputs/ta100/B10/I095/result.json",
    "result_sha256": "3947d6cc5d09ab063cf4ef825af8f2e348a0b3c7e963f0cc4f429b52365118d9",
    "fit_group_cv_gain": 4.206870220957448e-05
  },
  {
    "rank": 8,
    "representative_round": "I003",
    "members": [
      "I003"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_mean_length",
        "left": {
          "feature": "s_mean_length",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 2.5630158765375004
        },
        "right": {
          "feature": "td_phase_source_entropy",
          "left": {
            "action": "false"
          },
          "right": {
            "action": "true"
          },
          "threshold": 0.40352420417540247
        },
        "threshold": 2.673101892945
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.022517827027330073,
    "gain_vs_fixed_true": 0.03154918668175821,
    "exploratory_interval95_vs_old_static": [
      -0.0977550141142201,
      0.01630921191460556
    ],
    "result_path": "outputs/ta100/B01/I003/result.json",
    "result_sha256": "ee52194d74a556e72b4cb72d53a62affcf3916c16ac0d567be1590a89a577cf6",
    "fit_group_cv_gain": -0.0072594687714571116
  },
  {
    "rank": 9,
    "representative_round": "I066",
    "members": [
      "I066"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_mean_length",
        "left": {
          "feature": "s_mean_length",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 2.5630158765375004
        },
        "right": {
          "feature": "algebra_hall_deficiency",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.58056640625
        },
        "threshold": 2.673101892945
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.024712663802219703,
    "gain_vs_fixed_true": 0.029470404871252076,
    "exploratory_interval95_vs_old_static": [
      -0.10035702470592996,
      0.012509748385822554
    ],
    "result_path": "outputs/ta100/B07/I066/result.json",
    "result_sha256": "03e64019b5e9e4008b91ebeb301ec26846f21a6a9bdabc82d69b54448bc44d32",
    "fit_group_cv_gain": 0.007220279292573517
  },
  {
    "rank": 10,
    "representative_round": "I099",
    "members": [
      "I099"
    ],
    "policy": {
      "baseline_action": "true",
      "tree": {
        "feature": "s_mean_length",
        "left": {
          "feature": "s_mean_length",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 2.5630158765375004
        },
        "right": {
          "feature": "td_glue_size_dependence",
          "left": {
            "action": "true"
          },
          "right": {
            "action": "false"
          },
          "threshold": 0.751223465906
        },
        "threshold": 2.673101892945
      },
      "fallback_policy": null,
      "required_dynamic_features": null
    },
    "gain_vs_old_static": -0.025026782725233288,
    "gain_vs_fixed_true": 0.029172895411338273,
    "exploratory_interval95_vs_old_static": [
      -0.10055295040804983,
      0.012785426986783283
    ],
    "result_path": "outputs/ta100/B10/I099/result.json",
    "result_sha256": "bc0341b33fb686eeb2865fce65cfe141228df62498ba703fc54236545af677f8",
    "fit_group_cv_gain": 0.0
  }
]
''')

def choose_phase(rank, features, eligible=True):
    if type(rank) is not int or not 1 <= rank <= 10:
        raise ValueError("rank must be1..10")
    policy = POLICIES[rank-1]["policy"]
    if not eligible:
        return policy["baseline_action"]
    node = policy["tree"]
    while "action" not in node:
        value = features.get(node["feature"])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return policy["baseline_action"]
        node = node["left"] if value <= node["threshold"] else node["right"]
    return node["action"]
