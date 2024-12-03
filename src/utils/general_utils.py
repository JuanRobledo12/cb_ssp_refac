import pandas as pd 
import os
import re
from cb_config import *
import yaml


class PreprocessingUtils:
    
    def __init__(self) -> None:
        pass

    def build_path(self, PATH):
        return os.path.abspath(os.path.join(*PATH))
    
    def load_parameters_from_yaml(self, yaml_file_path):
        """
        Loads parameters from a YAML file.

        Parameters:
        yaml_file_path (str): Path to the YAML file.

        Returns:
        dict: A dictionary containing the loaded parameters.
        """
        try:
            with open(yaml_file_path, 'r') as file:
                params = yaml.safe_load(file)

            # Extract and validate required parameters
            required_keys = [
                'country_id',
                'attr_primary_file_name',
                'attr_strategy_file_name',
                'ssp_output_data_file_name',
                'comparison_strategy_code',
                'transformation_names_url'
            ]
            
            missing_keys = [key for key in required_keys if key not in params]
            if missing_keys:
                raise ValueError(f"Missing required parameters in YAML file: {', '.join(missing_keys)}")
            
            # Return the parameters as a dictionary
            return {key: params[key] for key in required_keys}
    
        except FileNotFoundError:
            raise FileNotFoundError(f"The specified YAML file was not found: {yaml_file_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML file: {e}")
            
    def merge_attribute_files(self, primary_filename : str, attribute_filename : str) -> pd.DataFrame:
        
        """
        Merges ATTRIBUTE_PRIMARY with ATTRIBUTE_STRATEGY on strategy_id

        returns a pd.DataFrame()
        """

        primary_attributes = pd.read_csv(primary_filename)
        strategy_attributes = pd.read_csv(attribute_filename)

        merged_attributes = primary_attributes.merge(right = strategy_attributes, on = "strategy_id")
        
        return merged_attributes
    
    
    def remove_suffix_from_transformations(self, attr_df):
        """
        Removes specific suffixes from the `transformation_specification` column of a DataFrame.

        Parameters:
        attr_df (pd.DataFrame): DataFrame containing the `transformation_specification` column.

        Returns:
        pd.DataFrame: A DataFrame with suffixes removed from the `transformation_specification` column.
        """
        df = attr_df.copy()

        # List of suffixes to remove
        suffixes_to_remove = [
            "_LOW", "_LOWEST", "_HIGHEST", "_HIGHER", "_HIGH", "_LOWER",
            "_FROMTECH", "_URBPLAN"
        ]

        # Compile regex pattern to match any of the suffixes at the end of a word
        pattern = re.compile(r'(' + '|'.join(re.escape(suffix) for suffix in suffixes_to_remove) + r')$')

        # Function to clean transformation specifications
        def clean_transformation_specification(specification):
            transformations = specification.split('|')  # Split by |
            cleaned_transformations = [
                re.sub(pattern, '', t) for t in transformations
            ]
            return '|'.join(cleaned_transformations)

        # Apply the cleaning function to the transformation_specification column
        df['transformation_specification'] = df['transformation_specification'].apply(clean_transformation_specification)

        return df

    def check_missing_transformations(self, attributes_df, transformation_cost_definitions):
        """
        Checks for missing transformations in the transformation cost definitions.

        Parameters:
        attributes_df (pd.DataFrame): DataFrame containing the 'transformation_specification' column.
        transformation_cost_definitions (pd.DataFrame): DataFrame containing the 'transformation_code' column.

        Returns:
        None: Prints a report of missing transformations and writes them to a CSV file.
        """
        # Extract transformations from attributes_df
        transformations_series = attributes_df['transformation_specification'].dropna()  # Ensure no NaN values
        experiment_transformations = set(
            val for row in transformations_series for val in row.split('|')
        )
        
        # Extract transformations from transformation_cost_definitions
        tf_costs_transformations = set(transformation_cost_definitions['transformation_code'])
        
        # Identify missing transformations
        missing_transformations = experiment_transformations - tf_costs_transformations
        missing_transformations = sorted(missing_transformations)
        
        if missing_transformations:
            # Create a DataFrame for missing transformations
            df = pd.DataFrame(missing_transformations, columns=['missing_transformations'])
            
            # Print missing transformations
            print(
                "The following transformations are not in the transformation_cost_definitions file. "
                "Please update it to avoid affecting the calculation of transformation costs:\n",
                missing_transformations
            )
            
            # Save the report to a CSV file
            output_path = 'debug/missing_transformations_report.csv'
            df.to_csv(output_path, index=False)
            print(f"Missing transformations report saved to: {output_path}")
        else:
            print("No missing transformations. OK!")

    def get_cols_to_keep(self, col_names):

        """
        Eliminates data of furnace gas and crude (TONY: Not sure what this is about)
        """
        cols_to_keep = [string for string in col_names if not re.match(re.compile('totalvalue.*furnace_gas'), string)]
        cols_to_keep = [string for string in cols_to_keep if not re.match(re.compile('totalvalue_.*_fuel_consumed_.*_fuel_crude'), string)]
        cols_to_keep = [string for string in cols_to_keep if not re.match(re.compile('totalvalue_.*_fuel_consumed_.*_fuel_electricity'), string)] #10.13 ADDED THIS SO SECTOR FUELS EXCLUDE ELECTRICITY

        return cols_to_keep
    
    def add_total_tlu_calculation(self, df, tlu_conversions_df, cols_to_keep):

        cb_input_df = df.copy()
        pop_livestock = cb_input_df[SSP_GLOBAL_SIMULATION_IDENTIFIERS + [i for i in cols_to_keep if "pop_lvst" in i]] # Obtained from cb_config.py
        pop_livestock = pop_livestock.melt(id_vars=['primary_id', 'time_period', 'region', 'strategy_code', 'future_id'])
        pop_livestock = pop_livestock.merge(right=tlu_conversions_df, on = "variable")

        pop_livestock["total_tlu"] = pop_livestock["value"] * pop_livestock["TLU"]

        pop_livestock_summarized = pop_livestock.groupby(SSP_GLOBAL_SIMULATION_IDENTIFIERS).\
                                                    agg({"total_tlu" : sum}).\
                                                    rename(columns={"total_tlu":"lvst_total_tlu"}).\
                                                    reset_index()

        return cb_input_df.merge(right = pop_livestock_summarized, on = SSP_GLOBAL_SIMULATION_IDENTIFIERS)
    
    
    def fetch_csv_from_github(self, url):
        """
        Fetches a CSV file from a GitHub URL and loads it into a pandas DataFrame.
        Raises an error if the DataFrame is empty.

        Parameters:
        url (str): The raw URL to the CSV file on GitHub.

        Returns:
        pd.DataFrame: A pandas DataFrame containing the contents of the CSV file.

        Raises:
        ValueError: If the DataFrame is empty.
        """
        # Convert the GitHub URL to the raw file URL
        raw_url = url.replace('/blob/', '/').replace('github.com', 'raw.githubusercontent.com')
        
        try:
            # Read the CSV file into a pandas DataFrame
            df = pd.read_csv(raw_url)
            
            # Check if the DataFrame is empty
            if df.empty:
                raise ValueError(f"The CSV file fetched from {raw_url} is empty.")
            
            print(f"Successfully fetched CSV file from: {raw_url}")
            return df
        except Exception as e:
            print(f"Error fetching CSV file from {raw_url}: {e}")
            return None
    
    def get_default_transformation_codes(self, transformer_df):
        """
        Processes the transformer codes by removing 'TFR:BASE' and replacing the 'TFR' prefix with 'TX'.

        Parameters:
        transformer_df (pd.DataFrame): DataFrame containing a 'transformer_code' column.

        Returns:
        list: A list of processed transformer codes.
        """
        # Get the transformer codes as a list
        column_names = transformer_df['transformer_code'].tolist()

        # Remove 'TFR:BASE' if it exists in the list
        if 'TFR:BASE' in column_names:
            column_names.remove('TFR:BASE')

        # Replace 'TFR' prefix with 'TX' in all codes
        column_names = [code.replace('TFR:', 'TX:') for code in column_names]

        return column_names
    
    
    def build_attribute_strategy_code(self, url, strategies_list, attr_data_df):
        """
        Creates a DataFrame based on transformation specifications and global strategies.

        Parameters:
        column_names_url (str): The raw URL to the GitHub CSV file for column names.
        strategies_list (list): A list of strategy codes to populate the `strategy_code` column.
        attr_data_df (pd.DataFrame): DataFrame containing the `transformation_specification` column.

        Returns:
        pd.DataFrame: A DataFrame with strategy codes and transformations as 0 or 1.
        """
        # Step 1: Fetch column names from the GitHub CSV file
        transformer_df = self.fetch_csv_from_github(url)
        column_names = self.get_default_transformation_codes(transformer_df)
        
        # Step 2: Initialize the DataFrame
        df = pd.DataFrame(0, index=strategies_list, columns=['strategy_code'] + column_names)
        df['strategy_code'] = strategies_list

        # Step 3: Populate the DataFrame with 1s based on transformations
        for strategy_code in strategies_list:
            # Filter the input DataFrame for the current strategy
            strategy_row = attr_data_df[attr_data_df['strategy_code'] == strategy_code]

            if not strategy_row.empty:
                # Get the transformation_specification
                transformations = strategy_row['transformation_specification'].iloc[0]

                if pd.notna(transformations):
                    # Split the transformations by the pipe symbol
                    transformation_list = transformations.split('|')

                    # Mark the corresponding columns as 1 if they match a column name
                    for transformation in transformation_list:
                        if transformation in column_names:
                            df.loc[df['strategy_code'] == strategy_code, transformation] = 1
        
        df.reset_index(drop=True, inplace=True)
        return df
    
    
    def build_strategy_cost_instructions(self, strategies_list, comparison_code):
        """
        Builds a DataFrame to represent strategy cost instructions.

        Parameters:
        strategies_list (list): A list of strategy codes to populate the `strategy_code` column.
        comparison_code (str or int): The value to populate the `comparison_code` column.

        Returns:
        pd.DataFrame: A DataFrame with strategy codes and cost evaluation instructions.
        """
        # Init df
        df = pd.DataFrame({
            'strategy_code': strategies_list,
            'comparison_code': comparison_code,
            'evaluate_system_costs': 1,
            'evaluate_transformation_costs': 1
        })

        # Reset the index to ensure numerical indexing
        df.reset_index(drop=True, inplace=True)

        return df
    

    def perform_postprocessing(self, results_all_pp):
        #POST PROCESS TRANSPORT CB ISSUES (These should be addressed properly in the next round of analysis)
        #congestion and safety benefits should be 0 in strategies that only make fuel efficiency gains and fuel switching

        df = results_all_pp.copy()

        cond_transport_cb_issues_better_base = (df["strategy_code"]=="PFLO:BETTER_BASE") & (df["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))
        cond_transport_cb_issues_supply_side_tech = (df["strategy_code"]=="PFLO:SUPPLY_SIDE_TECH") & (df["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))

        df.loc[cond_transport_cb_issues_better_base, "value"] = 0.0
        df.loc[cond_transport_cb_issues_supply_side_tech, "value"] = 0.0

        #in ALL, cut the benefits in half to be on the safe side.
        cond_cut_ben_in_half_all_plur =  (df["strategy_code"]=="PFLO:ALL_PLUR") & (df["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))
        cond_cut_ben_in_half_all_non_stopping_def_plur =  (df["strategy_code"]=='PFLO:ALL_NO_STOPPING_DEFORESTATION_PLUR') & (df["variable"].apply(lambda x : any(k in x for k in ["congestion", "road_safety"])))

        df.loc[cond_cut_ben_in_half_all_plur, "value"] *= 0.5 
        df.loc[cond_cut_ben_in_half_all_non_stopping_def_plur, "value"] *= 0.5 

        #POST PROCESS WASO CB ISSUES
        #where moving from incineration to landfilling appears to have benefits
        #when this move should probably not occur
        cond_waso_cb_issue =  (df["strategy_code"]=="PFLO:SUPPLY_SIDE_TECH") & (df["variable"].apply(lambda x : any(k in x for k in ["cb:waso:technical_cost:waste_management"])))
        df.loc[cond_waso_cb_issue, "value"] = 0.0


        #SHIFT any stray costs incurred from 2015 to 2025 to 2025 and 2035
        results_all_pp_before_shift = df.copy() #keep copy of earlier results just in case/for comparison
        res_pre2025 = df.query(f"time_period<{SSP_GLOBAL_TIME_PERIOD_TX_START}")#get the subset of early costs
        res_pre2025["variable"] = res_pre2025["variable"] + "_shifted" + (res_pre2025["time_period"]+SSP_GLOBAL_TIME_PERIOD_0).astype(str)#create a new variable so they can be recognized as shifted costs
        res_pre2025["time_period"] = res_pre2025["time_period"]+SSP_GLOBAL_TIME_PERIOD_TX_START #shift the time period

        df = pd.concat([df, res_pre2025], ignore_index = True) #paste the results

        df.loc[df["time_period"]<SSP_GLOBAL_TIME_PERIOD_TX_START,'value'] = 0 #set pre-2025 costs to 0

        return df


