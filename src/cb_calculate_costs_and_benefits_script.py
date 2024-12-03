#-------------SOURCE LIBRARIES AND CODE-----
#source('cb_config.R')
#source('cb_utilities.R')
#source('cb_strategy_specific_functions.R')
#source('general_ssp_utilities.R')

from utils.general_utils import *
from cb_config import *
from cb_utilities import cb_calculate_system_costs, cb_calculate_transformation_costs,cb_process_interactions
from data_reader import CBFilesReader
from cb_config import * 
import pickle

from typing import List
import pandas as pd 
import os 
import re 
import numpy as np

def build_path(PATH : List[str]) -> str:
    return os.path.abspath(os.path.join(*PATH))

#-------------READ THE DATA-----------------
## ----------- DEFINE PATHS
CB_REFAC_PATH = build_path([os.getcwd(), ".."])
CB_REFAC_DATA_PATH = build_path([CB_REFAC_PATH, "data"])
STRATEGY_SPECIFIC_CB_PATH_FILES = build_path([CB_REFAC_DATA_PATH, "strategy_specific_cb_files"])
#SSP_RESULTS_DATA_PATH = build_path([CB_REFAC_DATA_PATH, "ssp_model_results"])
SSP_RESULTS_DATA_PATH = build_path([CB_REFAC_DATA_PATH, "ssp_model_results", "iran"])
DEFINITION_FILES_PATH = build_path([CB_REFAC_DATA_PATH, "definition_files"])

OUTPUT_PATH = build_path([CB_REFAC_PATH, "output"])

#data_filename = build_path([SSP_RESULTS_DATA_PATH, "sisepuede_results_sisepuede_run_ssp.csv"] )
#data_filename = build_path([SSP_RESULTS_DATA_PATH, "sisepuede_results_sisepuede_run_iran.csv"] )
data_filename = build_path([SSP_RESULTS_DATA_PATH, "new_ssp_results.csv"] )
primary_filename = build_path([SSP_RESULTS_DATA_PATH, "ATTRIBUTE_PRIMARY_new.csv"])
strategy_filename = build_path([SSP_RESULTS_DATA_PATH, "ATTRIBUTE_STRATEGY_new.csv"])

output_file = pd.read_csv(data_filename)

#-------------PREPARE THE DATA--------------
#Read data
data = output_file.copy()


#Merge model output with strategy attributes (mainly the strategy_code)
run_attributes = ssp_merge_run_attributes(primary_filename, strategy_filename)
merged_data = run_attributes[['primary_id', 'strategy_code', 'future_id']].merge(right = data, on='primary_id')
data = merged_data.copy()

### Convertimos BASE ---> LNDU:PLUR
data.loc[data.strategy_code=='BASE', "strategy_code"]="LNDU:PLUR"

#clean the data of furnace gas and crude
temp_data_cols = data.columns

cols_to_keep = [string for string in temp_data_cols if not re.match(re.compile('totalvalue.*furnace_gas'), string)]
cols_to_keep = [string for string in cols_to_keep if not re.match(re.compile('totalvalue_.*_fuel_consumed_.*_fuel_crude'), string)]
cols_to_keep = [string for string in cols_to_keep if not re.match(re.compile('totalvalue_.*_fuel_consumed_.*_fuel_electricity'), string)] #10.13 ADDED THIS SO SECTOR FUELS EXCLUDE ELECTRICITY

data = data[cols_to_keep]

#add calculation of total TLUs to data
TLU_CONVERSION_FILE_PATH = build_path([STRATEGY_SPECIFIC_CB_PATH_FILES, "lvst_tlu_conversions.csv"]) 
tlu_conversions = pd.read_csv(TLU_CONVERSION_FILE_PATH)

pop_livestock = data[SSP_GLOBAL_SIMULATION_IDENTIFIERS + [i for i in cols_to_keep if "pop_lvst" in i]]
pop_livestock = pop_livestock.melt(id_vars=['primary_id', 'time_period', 'region', 'strategy_code', 'future_id'])
pop_livestock = pop_livestock.merge(right=tlu_conversions, on = "variable")

pop_livestock["total_tlu"] = pop_livestock["value"] * pop_livestock["TLU"]

pop_livestock_summarized = pop_livestock.groupby(SSP_GLOBAL_SIMULATION_IDENTIFIERS).\
                                            agg({"total_tlu" : sum}).\
                                            rename(columns={"total_tlu":"lvst_total_tlu"}).\
                                            reset_index()

data = data.merge(right = pop_livestock_summarized, on = SSP_GLOBAL_SIMULATION_IDENTIFIERS)

#replace any lagging references to "PFLO:SOCIOTECHNICAL" with "PFLO:CHANGE_CONSUMPTION"
data.loc[data["strategy_code"] == "PFLO:SOCIOTECHNICAL", "strategy_code"] = "PFLO:CHANGE_CONSUMPTION"
SSP_GLOBAL_list_of_strategies = data["strategy_code"].unique()
SSP_GLOBAL_list_of_variables = list(set(data.columns) - set(SSP_GLOBAL_SIMULATION_IDENTIFIERS))

#-------------REMOVE BASE FOR COST BENEFIT ANALYSIS------------
data = data.query("strategy_code!='BASE'").reset_index(drop=True)

#data[""]{i:j for i,j in pd.read_csv(primary_filename)[["primary_id", "strategy_id"]].to_records(index = False)}
#-------------READ DEFINITION FILES IN AND CALCULATE COSTS AND BENEFITS----------

#maps strategies to transformations, from James
#This file tells us which transformation in is in each strategy
strategy2tx = pd.read_csv(build_path([DEFINITION_FILES_PATH, 'attribute_strategy_code.csv']))

## Agregamos las estrategias 6003 : 'PFLO:CONSTRAINED', 6004 : 'PFLO:TECHNOLOGICAL_ADOPTION',6005 :'PFLO:UNCONSTRAINED'
#STRATEGY_DEFINITION_FILE_PATH = build_path([SSP_RESULTS_DATA_PATH, "strategy_definitions.csv"])
STRATEGY_DEFINITION_FILE_PATH = build_path([SSP_RESULTS_DATA_PATH, "ATTRIBUTE_STRATEGY.csv"])
ssp_strategy_definition_james = pd.read_csv(STRATEGY_DEFINITION_FILE_PATH)

actualiza_claves_tx  = {'TX:AGRC:EXPAND_CONSERVATION_AGRICULTURE' : 'TX:AGRC:INC_CONSERVATION_AGRICULTURE',
 #'TX:AGRC:INC_RESIDUE_REMOVAL' : ,
 #'TX:AGRC_DEC_DEMAND_FOR_UNHEALTHY_CROPS',
 'TX:CCSQ:INCREASE_CAPTURE' : 'TX:CCSQ:INC_CAPTURE',
 #'TX:ENTC:LEAST_COST',
 'TX:ENTC:TARGET_RENEWABLE_ENERGY_PRODUCTION' : 'TX:ENTC:TARGET_RENEWABLE_ELEC',
 #'TX:GNRL:DEC_RED_MEAT_CONSUMPTION',
 'TX:INEN:FUEL_SWITCH_HI_AND_LO_HEAT' : 'TX:INEN:SHIFT_FUEL_HEAT',
 #'TX:INEN:FUEL_SWITCH_HI_HEAT',
 #'TX:INEN:FUEL_SWITCH_LO_HEAT',
 'TX:LNDU:DEC_DEFORESTATION_AND_INC_SILVOPASTURE' : 'TX:LNDU:DEC_DEFORESTATION',
  'TX:LNDU:DEC_DEFORESTATION' : 'TX:LNDU:DEC_DEFORESTATION',
 #'TX:LNDU:INC_LAND_REHABILITIATION',
 'TX:PFLO:IND_INC_CCS' : 'TX:PFLO:INC_IND_CCS',
 'TX:SCOE:FUEL_SWITCH_HEAT' : 'TX:SCOE:SHIFT_FUEL_HEAT',
 'TX:SOIL:DEC_LIME_APPLIED' : 'TX:SOIL:DEC_LIME_APPLIED_HIGHEST',
 'TX:SOIL:DEC_N_APPLIED' : 'TX:SOIL:DEC_N_APPLIED_HIGHEST',
 'TX:TRNS:FUEL_SWITCH_LIGHT_DUTY' : 'TX:TRNS:SHIFT_FUEL_LIGHT_DUTY',
 'TX:TRNS:FUEL_SWITCH_MARITIME' : 'TX:TRNS:SHIFT_FUEL_MARITIME',
 'TX:TRNS:FUEL_SWITCH_MEDIUM_DUTY' : 'TX:TRNS:SHIFT_FUEL_MEDIUM_DUTY',
 'TX:TRNS:FUEL_SWITCH_RAIL' : 'TX:TRNS:SHIFT_FUEL_RAIL',
 'TX:TRNS:INC_EFFICIENCY' : 'TX:TRNS:INC_EFFICIENCY_NON_ELECTRIC',
 'TX:TRNS:INC_OCCUPANCY' : 'TX:TRNS:INC_OCCUPANCY_LIGHT_DUTY',
 'TX:TRNS:MODE_SHIFT_FREIGHT' : 'TX:TRNS:SHIFT_MODE_FREIGHT',
 'TX:TRNS:MODE_SHIFT_PASSENGER' : 'TX:TRNS:SHIFT_MODE_PASSENGER',
 'TX:TRNS:MODE_SHIFT_REGIONAL' : 'TX:TRNS:SHIFT_MODE_REGIONAL'}
 
actualiza_claves_tx = {j:i for i,j in actualiza_claves_tx.items()}

def quita_sufijo(tx_nombre : str) -> str:
    for sufijo in ["_LOW","_LOWEST","_HIGHEST","_HIGHER", "_HIGH", "_LOWER","_FROMTECH", "_URBPLAN"]:
        if tx_nombre.endswith(sufijo):
            tx_nombre = tx_nombre.replace(sufijo, "")

    return tx_nombre

for id_tx in ['PFLO:CONSTRAINED', 'PFLO:UNCONSTRAINED', 'PFLO:NET_ZERO']:
    tx_in_strat = ssp_strategy_definition_james.set_index("strategy_code").loc[id_tx, "transformation_specification"].split("|")
    df_new_strat_name = pd.DataFrame({"strategy_code" : [id_tx]})
    df_binary_tx = pd.DataFrame([[1]*len(tx_in_strat)] , columns=tx_in_strat)
    df_new_strat = pd.concat([df_new_strat_name, df_binary_tx], axis = 1)
    df_new_strat.columns = [quita_sufijo(i) for i in df_new_strat.columns]

    df_new_strat = df_new_strat.rename(columns = actualiza_claves_tx)

    columnas_coinciden = list(set(strategy2tx.columns).intersection(df_new_strat.columns))
    strategy2tx = pd.concat([strategy2tx, df_new_strat[columnas_coinciden]], ignore_index = True)

strategy2tx = strategy2tx.replace(np.nan, 0)

"""
nuevas_strategy2tx = []

mapp_id2codename = {
     6003 : 'PFLO:CONSTRAINED', 
     6004 : 'PFLO:TECHNOLOGICAL_ADOPTION',
     6005 :'PFLO:UNCONSTRAINED'
}

for id_tx in [6003, 6004, 6005]:
    nuevas_strategy2tx.append(
        [mapp_id2codename[id_tx]] + [int(i in ssp_strategy_definition_james.set_index("strategy_id").loc[id_tx].transformation_specification.split("|")) for i in strategy2tx.columns[1:] ]
    )

nuevas_strategy2tx = pd.DataFrame(nuevas_strategy2tx, columns=strategy2tx.columns)
strategy2tx = pd.concat([strategy2tx, nuevas_strategy2tx], ignore_index = True)

"""

#tells us which strategies to evaluate costs and benefit iffor
mapp_id2codename = {
     6003 : 'PFLO:CONSTRAINED', 
     6004 : 'PFLO:UNCONSTRAINED',
     6005 :'PFLO:NET_ZERO'
}


strategy_cost_instructions = pd.read_csv(build_path([DEFINITION_FILES_PATH, 'strategy_cost_instructions.csv']))

new_strategy_cost_instructions = pd.DataFrame(
    [
       [mapp_id2codename[id_tx]]*2 + ["LNDU:PLUR",1,1]  for id_tx in [6003, 6004, 6005]
    ],
    columns = ['strategy', 'strategy_code', 'comparison_code', 'evaluate_system_costs','evaluate_transformation_costs']
)

strategy_cost_instructions = pd.concat([strategy_cost_instructions, new_strategy_cost_instructions], ignore_index=True)

#the list of all the cost factor files in the system, and the functions they should be evaluated with
cost_factor_names = pd.read_csv(build_path([DEFINITION_FILES_PATH, 'system_cost_factors_list.csv']))  

#defines how each transformation is evaluated, including difference variables, cost multipliers, etc.
transformation_cost_definitions = pd.read_csv(build_path([DEFINITION_FILES_PATH, 'transformation_cost_definitions.csv']), encoding="latin")

#calculate system costs
cb_data = CBFilesReader(CB_REFAC_DATA_PATH)

print(
    """
    ++++++++++++++++++++++++++++++++++++++++++++++++++++
    
                    CALCULATE SYSTEM COST

    +++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
)
results_system = cb_calculate_system_costs(data, strategy_cost_instructions, cost_factor_names, cb_data, SSP_GLOBAL_list_of_variables, SSP_GLOBAL_list_of_strategies)

#calcualte transformation costs

print(
    """
    ++++++++++++++++++++++++++++++++++++++++++++++++++++
    
                    CALCULATE TRANSFORMATION COST

    +++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
)

results_tx = cb_calculate_transformation_costs(data, 
                                  strategy_cost_instructions,
                                  strategy2tx, 
                                  transformation_cost_definitions, 
                                  cb_data,
                                  SSP_GLOBAL_list_of_variables, 
                                  SSP_GLOBAL_list_of_strategies)

RESULTS_SYSTEMS_PATH = build_path([OUTPUT_PATH, "python", "results_system_python.csv"])
RESULTS_TX_SYSTEMS_PATH = build_path([OUTPUT_PATH, "python", "results_tx_python.csv"])


#combine the results
results_all = pd.concat([results_system, results_tx], ignore_index = True)

SSP_GLOBAL_list_of_cbvars = results_all["variable"].unique()


#-------------POST PROCESS SIMULATION RESULTS---------------
#Post process interactions among strategies that affect the same variables
postprocess_interactions = pd.read_csv(build_path([DEFINITION_FILES_PATH, 'strategy_interaction_definitions.csv']))

results_all_pp = cb_process_interactions(results_all, strategy2tx, postprocess_interactions)

#POST PROCESS TRANSPORT CB ISSUES (These should be addressed properly in the next round of analysis)
#congestion and safety benefits should be 0 in strategies that only make fuel efficiency gains and fuel switching

cond_transport_cb_issues_better_base = (results_all_pp["strategy_code"]=="PFLO:BETTER_BASE") & (results_all_pp["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))
cond_transport_cb_issues_supply_side_tech = (results_all_pp["strategy_code"]=="PFLO:SUPPLY_SIDE_TECH") & (results_all_pp["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))

results_all_pp.loc[cond_transport_cb_issues_better_base, "value"] = 0.0
results_all_pp.loc[cond_transport_cb_issues_supply_side_tech, "value"] = 0.0

#in ALL, cut the benefits in half to be on the safe side.
cond_cut_ben_in_half_all_plur =  (results_all_pp["strategy_code"]=="PFLO:ALL_PLUR") & (results_all_pp["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))
cond_cut_ben_in_half_all_non_stopping_def_plur =  (results_all_pp["strategy_code"]=='PFLO:ALL_NO_STOPPING_DEFORESTATION_PLUR') & (results_all_pp["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))

results_all_pp.loc[cond_cut_ben_in_half_all_plur, "value"] *= 0.5 
results_all_pp.loc[cond_cut_ben_in_half_all_non_stopping_def_plur, "value"] *= 0.5 

#POST PROCESS WASO CB ISSUES
#where moving from incineration to landfilling appears to have benefits
#when this move should probably not occur
cond_waso_cb_issue =  (results_all_pp["strategy_code"]=="PFLO:SUPPLY_SIDE_TECH") & (results_all_pp["variable"].apply(lambda x : any(k in x for k in ["cb:waso:technical_cost:waste_management"])))
results_all_pp.loc[cond_waso_cb_issue, "value"] = 0.0


#SHIFT any stray costs incurred from 2015 to 2025 to 2025 and 2035
results_all_pp_before_shift = results_all_pp.copy() #keep copy of earlier results just in case/for comparison
res_pre2025 = results_all_pp.query(f"time_period<{SSP_GLOBAL_TIME_PERIOD_TX_START}")#get the subset of early costs
res_pre2025["variable"] = res_pre2025["variable"] + "_shifted" + (res_pre2025["time_period"]+SSP_GLOBAL_TIME_PERIOD_0).astype(str)#create a new variable so they can be recognized as shifted costs
res_pre2025["time_period"] = res_pre2025["time_period"]+SSP_GLOBAL_TIME_PERIOD_TX_START #shift the time period

results_all_pp = pd.concat([results_all_pp, res_pre2025], ignore_index = True) #paste the results

results_all_pp.loc[results_all_pp["time_period"]<SSP_GLOBAL_TIME_PERIOD_TX_START,'value'] = 0 #set pre-2025 costs to 0


#Write
CB_OUTPUT_FILENAME = build_path([OUTPUT_PATH, "cost_benefit_results.csv"])
results_all_pp.to_csv(CB_OUTPUT_FILENAME, index = False)

#results_system.to_csv(RESULTS_SYSTEMS_PATH, index = False)
#results_tx.to_csv(RESULTS_TX_SYSTEMS_PATH, index = False)


"""
with open('args_container_3.pickle', 'rb') as handle:
    args_container_to_function_param = pickle.load(handle)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("task_app")

DATA_FILE_PATH = "/home/milo/Documents/egtp/SISEPUEDE/COST_BENEFITS/refactorizacion/local/data"
cb_reader = CBFilesReader(DATA_FILE_PATH, logger)
"""

# crops_vars = [i for i in df.variable.unique() if "cb:agrc:crop_value:crops_produced:" in i]

# crops_vars = [i for i in df["variable"].unique() if "productivity" in i]

# for crop in crops_vars:

#     consulta = f"sector =='agrc' and cb_type=='capex' and variable =='{crop}'"
#     cb_cols = ["strategy_code", "Year", "value"]
#     df.query(consulta)[cb_cols].pivot(index = "Year", columns = "strategy_code", values = "value").plot.bar(rot=0, title = crop)
#     plt.show()
