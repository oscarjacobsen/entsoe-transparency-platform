

# Main script containting module for interaction with Entso-E Transparency Platform

# Local imports

from get_api_statics import 


# Lib imports

from datetime import datetime, timedelta
import datetime
import difflib, io
import requests
import pandas as pd
import bs4
from bs4 import NavigableString
import json
import geopandas as gpd
import pandas as pd
import numpy as np
from ratelimit import limits
import unicodedata
import re
import zipfile



class EntsoeTransparencyClient():
    '''
    Pythonic client-module for easy, reliable access to Entso-E Transparency Platform Datasets.
    service_url: https://transparency.entsoe.eu/

    :Explained:
        -Always up-to-date: Retrieves api-static parameters from webscraping url html api-guide web page.
        -Matched requests: Finds best "close-match" in available parameters from user inputs to .get_data() request.
        -Fixed requests: If possible, fixes and re-runs request if initial request gave bad response.
        -Unzip zip: Unzips zipped document response, and includes in dataframe.
    
    
    '''
    
    #####################
    # Init functions
    #####################
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.api_url = f'https://transparency.entsoe.eu/api?'

        # Getting API guide requests and parameters from
        # Webscraping html api-guide url.
        self.datasets, self.parameters = self._get_statics_datasets_parameters()
        
        self.areas = self._get_entsoe_areas()


        return None


    def _parse_entsoe_response_to_df(self, soup_parent, start_tag="", df=pd.DataFrame([]), c_layer=0, layer_children=None):
        '''Helperfunction, recursively parse entso-e api response to pd.DataFrame.'''

        # If input is not soup, make soup.
        if isinstance(soup_parent, str):
            soup_parent = bs4.BeautifulSoup(soup_parent, features="lxml")
        elif isinstance(soup_parent, requests.Response):
            soup_parent = bs4.BeautifulSoup(soup_parent.text, features="lxml")
    
        # If start_tag is not None, this is first run.
        if start_tag is not None:

            # If spesified start_tag is not empty string
            if len(start_tag) > 0:

                # Ensure starttag is lowered as response tags are all lowered.
                start_tag = start_tag.lower()

                # Set spesified start_tag as soup_parent
                soup_parent = soup_parent.find(start_tag)
            
            # If spesified start_tag is empty string.
            else:

                # Find response body.
                body = soup_parent.find("body")

                # Set first tag after body, the response document type, as default parsing start parent.
                for child in body.children:
                    soup_parent = child
                    break
        
            # Initiate counter to keep track on present recursive layer through parsing.
            c_layer = 0

        # Increment layer counter and start search in soup_parent's children.
        c_layer += 1
        for child in soup_parent.children:
            #print(child.name)
            # Skipping bastard children.
            if child.name == None or child.name == '\n':
                continue
        
            # If: this child has multiple descendants, recursively walk down to childs childs childrens layer.
            if len(list(child.descendants)) > 1:

                # Include df in walk down and return from layer.
                df  = self._parse_entsoe_response_to_df(soup_parent=child, df=df, start_tag=None)
            
                # Returned from level, decrement level counter
                c_layer -= 1
        
            # Else: no descendants, add childs content to df. and new child name, add to df.columns as combo of parent and childs name.
            else:
            
                # Content name is combo of parent and childs name.
                column = str(soup_parent.name) + "-" + str(child.name)
            
                # Content value is childs content.
                value = str(child.string)
            
                # If: column not in df.columns, add as new column.
                if column not in df.columns:
                    df[column] = ""
                
                    # If: first input, df has no index, add value directly.
                    if len(df.index.values.tolist()) < 1:
                        df[column] = [value]
                
                    # Else: find index of last row, add value to column cell at last row.
                    else:
                        rowidx = df.index.tolist()[-1]
                        df.at[rowidx, column] = value
            
                # Elif: column is in df.columns but column cell at last row already has content.
                elif pd.isnull(df.iloc[-1:][column].values.tolist()[0]) == False:
                
                    # Append new empty row at end of df for storing new row of data.
                    df = df.append(pd.Series(dtype = 'object'), ignore_index=True)
                
                    # Copy data from upstream level columns to upstream cells in the new empty row in loop.
                    rowidx = df.index.tolist()[-1]
                    cols_list = df.columns.values.tolist()
                    for col_c in range(len(cols_list)):
                        df.at[rowidx, cols_list[col_c]] = df.at[rowidx-1, cols_list[col_c]]
                    
                        # If: loop reached the column of new data content, add the new data in cell, break out of loop and stop copying.
                        if column == cols_list[col_c]:
                            df.at[rowidx, cols_list[col_c]] = value
                            break
            
                # Else: column is in df.columns, and is without content. 
                else:
                
                    # Add content to cell
                    rowidx = df.index.tolist()[-1]
                    df.at[rowidx, column] = value
                    
            
            
        # If returning from top layer, fix finished df before returning.
        if c_layer == 0:
            #df.drop(columns="mrid", axis=0, inplace=True)
            df.replace("", np.nan, inplace=True)
            df.drop_duplicates(inplace=True)

            # Loop on df columns.
            for column in df.columns:

                # Try if column string is valid float, then set as float.
                try:
                    float(df.at[0, column])
                    df[column] = df[column].astype(float)
                
                # If not, do nothing
                except ValueError:
                    None
                
                # Try if column string is valid integer, then set as integer.
                try:
                    int(df.at[0, column])
                    df[column] = df[column].astype(int)
                
                # If not, do nothing
                except ValueError:
                    None
                
    
        # Return one layer up.
        return df
    
    def remap_df_parameters(self, df, column_type_mapping = {}):
        '''Helperfunction for remapping response codes to meaning'''
    
        # Storing list of existing columns_names and api parameter_types.
        df_cols_list = df.columns.values.tolist()
        api_para_list = list(self.api_parameters.keys())
    
        # Loop on df rows by index.
        for idx in df.index:
        
            # Loop on spesified columns to type mappings.
            for column, paramtype in column_type_mapping.items():

                # If spesified column exist in df and spesified type exist in available parameter types.
                if column in df_cols_list and paramtype in api_para_list:
            
                # Make sure cell to remap has content, is not already remapped and not empty string.
                    if pd.isnull(df.at[idx, column]) == False and len(df.at[idx, column]) > 0:
                
                        # Make sure cell value is not already mapped:
                        if df.at[idx, column] not in list(self.api_parameters[paramtype].values()):
                    
                            # Remap cell value.
                            df.at[idx, column] = self.api_parameters[paramtype][df.at[idx, column]]
    
        # Return remapped df.
        return df

    ######################
    # Backend functions ##
    ######################

    @limits(calls=399, period=60) #max 400 calls pr minute or 10min ban..
    def _call_api(self, url=None, parameters_dict=None, msg=False):
        '''Make call to api limited to , return full respons.
        '''
        # if url spesified, set url directly
        if url is not None:
            get_url = url
        # if parameters spesified, construct url
        elif parameters_dict is not None:
            get_url = self._construct_api_call_url(parameters_dict=parameters_dict)
        #if no url or parameters, cannot make call, return None.
        else:
            return None

        if msg:
            print(f'Making request at url:\n{get_url}')

        #makes request
        response = requests.get(get_url) 
        return response, get_url

        #return request respons
        #return None

    def _construct_api_call_url(self, parameters_dict, api_key=None, baseurl=None):
        '''Constructs api call url from baseurl, api_key and parameters_dict.
        '''
        #adds baseurl
        if baseurl is None:
            call_url = self.api_url
        else:
            call_url = baseurl
        
        #adds api_key
        if api_key is None:
            api_key = self.api_key
        call_url = f'{call_url}securityToken={api_key}' #call_url + 'securityToken=' + api_key
        
        #adds parameters
        for key, value in parameters_dict.items():
            call_url = f'{call_url}&{key}={value}' # call_url + '&' + key + '=' + value #syntax: &key=value 

        #return call_url
        return call_url

    def _get_statics_guide_soup(self, setasattr=True):
        '''Scrape url statics guide html, return 'static-content' as soup object.'''
        statics_soup = bs4.BeautifulSoup(requests.get('https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html').text, "lxml").find(id="static-content")
        if setasattr:
            setattr(self, 'statics_soup', statics_soup)
        return statics_soup
    
    def _get_statics_datasets_parameters(self):
        '''
        Getting entsoe api service statics from the api guide webpage using webscraping.
        API guide url: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
        '''

        # Extract part of html content containing the static content.
        content_soup = self._get_statics_guide_soup().find(id="content")
        
        # Finding all headers. TODO: missing 1.4. Parameters due du it being nested in ulist. Content included in 1.3.
        headers = content_soup.find_all(lambda x: x.name in ['h2', 'h3', 'h4'] and len(x.string) > 2)
        
        # Extract content in guide chapters and appendix.
        soup_chapters = content_soup.find_all(class_="sect1")
        soup_ch1_ch2 = soup_chapters[:1] #incl: api_url, 
        soup_ch3 = soup_chapters[2]
        soup_ch4 = soup_chapters[3] #incl: possible requests with parameterspesifications and request structure examples.
        soup_apndxA = soup_chapters[4] #incl: parameterslists,
        soup_apndxB = soup_chapters[5]

        
        ##############################################################
        #ch4: extract possible requests, parameters and code examples#
        ##############################################################

        services_dict = {}
        # Find all tags for service domains.
        service_domains_soup = soup_ch4.find_all(lambda tag: tag.name == "h3" and "4." in tag.text and "Detailed guidelines and examples" not in tag.text and "A." not in tag.text)
        
        # Add the Service domains as keys in the services_dict.
        for domain in service_domains_soup:
            services_dict[domain.text] = ''

        #extract part with api_requests info
        requests_data = soup_ch4.find_all(class_="sect2")
        requests_data = requests_data[:8]

        #TODO: add request example structures
        #get list of requests_code_examples from POST examples, dont use GET examples as they vary in html-stylings......
        requests_structure = soup_ch4.find_all(lambda tag: tag.name=="code" and "POST" in tag.text and "java" not in tag.text)
        #print(requests_structure.contents)
        
        #filters and fixes request structure examples. this is based on GET...
        structure_list = []
        for structure in requests_structure:
            #if no multiple descendants: adds to list
            if len(list(structure.descendants)) == 1:
                if structure.contents[0] not in structure_list and len(structure.contents[0]) > 10: #fix: removes empty GET d.t. html-font block..
                    structure_list.append(structure.contents[0])
            
            #else: walk down tree and add descendant due to html-font block..
            else:
                for structure1 in structure:
                    if len(list(structure1.descendants)) == 1:
                        structure_list.append(structure1.contents[0])
            


        #make list of available request headers, fix text
        requests_headers = []
        for a in requests_data:
            a_headers = a.find_all(lambda tag:tag.name=="h4" and "A." not in tag.text and "B." not in tag.text)
            requests_headers.extend(a_headers)
    
        #fix text, store headers in (for now) empty dict
        api_requests = {}
        for c in range(len(requests_headers)):
            header_text = requests_headers[c].text
            header_text = header_text.replace('\u2009','')
            header_text = header_text.replace('\xa0','')
            header_text = header_text.replace('.','_')
            header_text = header_text.replace('&','_')
            header_text = header_text.replace(' ','_')
            header_text = header_text.replace('__','_')
            header_text = header_text #do not lower, lower only on search.
            requests_headers[c] = header_text
            api_requests[header_text] = None
            #datasets['name'].append(header_text)

        
        # Create datasets 
        data = content_soup.find_all(lambda tag:tag.name=="h4" and "A." not in tag.text and "B." not in tag.text)
        datasets = {}
        datasets['names'] = []
        datasets['get'] = []
        datasets['get_mandatorys'] = []
        datasets['get_constants'] = []
        for d in data:
            datasets['names'].append(d.string.replace('\xa0','').replace('\u2009',''))
            get_str = d.find_next(text=re.compile("documentType="))
            datasets['get'].append(get_str)
            param_str = get_str.split('?')[-1]
            para_str = param_str.split('&')
            constants = [x for x in para_str if 'Type' in x and not 'psr' in x]
            mandatorys = [x.split('=')[0] for x in para_str if 'psr' not in x and 'classification' not in x]

            # Replace timeinveral with PeriodStart and PeriodEnd.
            x = []
            for a in mandatorys:
                if a == 'TimeInterval':
                    x.append('periodStart')
                    x.append('periodEnd')
                else:
                    x.append(a)
            mandatorys = x


            datasets['get_constants'].append(constants)
            datasets['get_mandatorys'].append(mandatorys)
        
        #getting requests parameters info, mandatory, optional
        api_requests_keys = list(api_requests.keys())
        count=0
        datasets['mandatorys'] = []
        datasets['optionals'] = []
        datasets['info'] = []
        for a in range(len(requests_data)):
            requests_info = []
            requests_mandatory = []
            requests_optional = []
    
            #extract list of data on info, mandatory, optional
            requests_info_mandatory_optional_data = requests_data[a].find_all(class_="ulist")
    
            #make dict for storing parameters
            param = {} 
    
            #loop lists of data on info, mandatory, optional
            for b in range(len(requests_info_mandatory_optional_data)):
                requests_info = []
                requests_mandatory = []
                requests_optional = []
        
                #extract each textline on info, mandatory, optional
                requests_info_mandatory_optional = requests_info_mandatory_optional_data[b].find_all('p')
                
                #fix: if not key='Mandatory parameters' in list, skip this duplicate nested class_="ulist" 
                storedata=False
                for c in range(len(requests_info_mandatory_optional)):
                    if 'mandatory parameters' in requests_info_mandatory_optional[c].text.lower(): #skips each table in main table
                        storedata=True
                        
                # if not skipped, store info, mandatory, optional data
                if storedata and count <= (len(api_requests_keys)-1):
                    
                    #using flags to seperate data in different textstrings
                    infoflag=True
                    mandatoryflag=False

                    #loop on textstrings
                    for c in range(len(requests_info_mandatory_optional)):
                
                        #cleanup textstring
                        text_string = requests_info_mandatory_optional[c].text
                        text_string = text_string.replace('\xa0','')
                        text_string = text_string #this is parameters, do not lower, never alter parameters.
                
                        # if key='Mandatory' in textstring, set mandatoryflag and continue to next iter
                        if 'Mandatory' in text_string:
                            infoflag=False
                            mandatoryflag=True
                            continue
                
                        # if key='Optional' in textline, reset mandatoryflag and continue to next iter
                        elif 'Optional' in text_string:
                            mandatoryflag=False
                            continue
                
                        #store textlines based on key flags.
                        if infoflag:
                            requests_info.append(text_string)
                        elif mandatoryflag:
                            requests_mandatory.append(text_string)
                        else:
                            requests_optional.append(text_string)
                    
                    #store in parameter dict
                    param['info'] = requests_info
                    param['mandatorys'] = requests_mandatory
                    param['optionals'] = requests_optional
                    
                    datasets['info'].append(requests_info)
                    datasets['mandatorys'].append(requests_mandatory)
                    datasets['optionals'].append(requests_optional)
                    #param['structure'] = requests_structure[count] TODO: add when sorted above.
                    
                    #add to main dict
                    api_requests[api_requests_keys[count]] = param
                    count+=1

                    # Add constants to datasets

        
        # Fix datasets mandatorys
        mandatorys_list = []
        for idx in range(len(list(datasets['names']))):

            mandatorys = []
            for a in datasets['mandatorys'][idx]:
    
        
                for b in a.split(' '):
                    if 'Type' in b or 'Domain' in b or 'Start' in b or 'End' in b or 'Date' in b:
                        mandatorys.append(b)
                
            # remove duplicates in list
            mandatorys = list(dict.fromkeys(mandatorys))
            
            # Append to main list.
            mandatorys_list.append(mandatorys)

        #datasets['get_mandatorys'] = mandatorys_list

        #add main dict as attribute
        #setattr(self, 'requests', api_requests)
        setattr(self, 'datasets', datasets)

        ##################################################
        #apndxA: extract api parameters headers and tables#
        ##################################################
        param_headers = soup_apndxA.find_all(lambda tag:tag.name=="h3" and "A." in tag.text)
        param_tables = soup_apndxA.find_all("table")
        param_dflist = pd.read_html(str(param_tables))

        #remove small info tables and sort:
        templist = []
        a = 0
        for c in range(len(param_dflist)):
            if len(param_dflist[c]) > 2: #removes small unwanted texttables.
                param_dflist[c].columns = param_dflist[c].iloc[0] #add first row as columns
                param_dflist[c] = param_dflist[c].drop(0) #drop old first row
                #param_dflist[c] = param_dflist[c].applymap(str.lower) #ensure all strings lower
                param_dflist[c].name = param_headers[a].text #add list name as df.name
                a=a+1 #header counter
                templist.append(param_dflist[c])
        param_dflist = templist
        del templist

        #store in api_variables as nested dict.
        parameters = {}
        for df in param_dflist:
            df_name = df.name
            df_name = df_name.split(' ', 1)[1] #remove table number A.1, A.2 etc.
            df_name = df_name.split(', ', 1) #if multiple api arguments is same list of parameters, split and create one for each.
            df_dict = dict(zip(df.iloc[:,0],df.iloc[:,1]))
            for name in df_name:
                for keys, values in df_dict.items(): #cleanup unicode
                    keys = keys.replace('\xa0',' ')
                    values = values.replace('\xa0',' ')
                    df_dict[keys] = values
                parameters[name] = df_dict
                
        setattr(self, 'parameters', parameters)

        return datasets, parameters

        ######################################
        ######################################    
          
    def _reason_fix_request(self, reason_str): #TODO: not created yet.
        '''Fixes request if possible based on text in reason'''

        # If requested to many days:
        if 'allowed: ' in reason_str:
            val_unit = reason_str.split('allowed: ')[-1].split(',')[0].split(' ')
            print(f'ALLOWED: {val_unit[0]} in unit {val_unit[-1]}')
    
    def _get_dataset_mandatorys_dict(self, dataset):
        '''Creates dictionary of parameters to be included in request.'''

        # Create dict for storing dataset mandatorys.
        mandatorys_dict = {}

        # Get list index matching dataset.
        list_idx = self.datasets['names'].index(dataset)

        # Get list of mandatory parameters
        mandatorys = self.datasets['get_mandatorys'][list_idx]
        constants = self.datasets['get_constants'][list_idx]

        # Loop on constant strings.
        for m in mandatorys:

            # Add mandatory to dict.
            mandatorys_dict[m] = None

            # Loop on constants.
            for c in constants:
                if m.lower() in c.split('=')[0].lower():
                    mandatorys_dict[m] = c.split('=')[-1]

        # Dictionary of mandatorys in request.
        return mandatorys_dict
    
    def _fix_get_inputs(self, datasets, from_to_areas, start_end_times):
        '''Ensure correct inputs for request'''

        # Ensure input datasets is list for later looping.
        if isinstance(datasets, list) is False:
            datasets = [datasets]

        # Ensure from_to_areas is list for laterlooping.
        if isinstance(from_to_areas, list) is False:
            from_to_areas = [from_to_areas]

        # Ensure start_end_times is list for looping.
        if isinstance(start_end_times, list) is False:
            start_end_times = [start_end_times]

        # Loop on data in from_to_areas list, fix contents as from_to_lists.
        for idx in range(len(from_to_areas)):

            # If list data is not tuple or list.
            if isinstance(from_to_areas[idx], tuple) is False and isinstance(from_to_areas[idx], list) is False:

                # Create as tuple assuming data is from "value".
                from_to_areas[idx] = [from_to_areas[idx], None]

            # If data is tuple, change to list for later altering.
            if isinstance(from_to_areas[idx], tuple):

                from_to_areas[idx] = [from_to_areas[idx][0], from_to_areas[idx][-1]]
        
        # Loop on data in start_end_times list, fix contents as start_end_lists
        for idx in range(len(start_end_times)):

            # If list data is not tuple or list.
            if isinstance(start_end_times[idx], tuple) is False and isinstance(start_end_times[idx], list) is False:

                # Create as tuple assuming data is from "value".
                start_end_times[idx] = [start_end_times[idx], None]

            # If data is tuple, change to list for later altering.
            if isinstance(start_end_times[idx], tuple):

                start_end_times[idx] = [start_end_times[idx][0], start_end_times[idx][-1]]
        
        #######################
        ## Fix datasets_list ##
        #######################

        # Find matching requesting datasets names.
        #datasets_list = []
        for idx in range(len(datasets)):
            datasets[idx] = self.find_dataset_match(dataset=datasets[idx])
            #datasets_list.append() 


        ##############################
        ## Fix start_stop_times_list##
        ##############################

        timeformat = '%Y%m%d%H%M'

        # If to time is not spesified, set to now.
        # If input to_time is string., ensure correct format.
        for idx in range(len(start_end_times)):

            # If start_time is str.
            if isinstance(start_end_times[idx][0], str):

                # Remove letters.
                start_end_times[idx][0] = start_end_times[idx][0].replace(' ','').replace('-','').replace(':', '')
            
                # Find string format.
                tform = '%Y%m%d%H%M%S'[:len(start_end_times[idx][0])-2]

                # Make as datetime.
                start_time_dt = datetime.datetime.strptime(start_end_times[idx][0], tform)

                # Make as stringtime.
                start_end_times[idx][0] = datetime.datetime.strftime(start_time_dt, timeformat)
        
            # If not spesified from_time, set time to 2 days ago.
            elif start_end_times[idx][0] is None:
                start_end_times[idx][0] = (datetime.datetime.now() - datetime.timedelta(2)).strftime("%Y%m%d%H")
                start_time_dt = datetime.datetime.strptime(start_end_times[idx][0], '%Y%m%d%H')
                start_end_times[idx][0] = datetime.datetime.strftime(start_time_dt, timeformat)

            # If end time is string.
            if isinstance(start_end_times[idx][-1], str):

                # Remove letters from timestring.
                start_end_times[idx][-1] = start_end_times[idx][-1].replace(' ','').replace('-','').replace(':', '')
                tform = '%Y%m%d%H%M%S'[:len(start_end_times[idx][-1])-2]
                stop_time_dt = datetime.datetime.strptime(start_end_times[idx][-1], tform)
                start_end_times[idx][-1]  = datetime.datetime.strftime(stop_time_dt, timeformat)

            if start_end_times[idx][-1] is None:
                start_end_times[idx][-1] = (datetime.datetime.now() - datetime.timedelta(1)).strftime("%Y%m%d%H")
                stop_time_dt = datetime.datetime.strptime(start_end_times[idx][-1], '%Y%m%d%H')
                start_end_times[idx][-1] = datetime.datetime.strftime(stop_time_dt, timeformat)
        

        ###############################
        ## Fix from_to_areas_list ##
        ###############################

        # Create new list for storing from_to_codes.
        from_to_codes = []

        # Loop on from_to_areas list.
        for idx in range(len(from_to_areas)):

            # Append empty list to new from_to_codes list.
            from_to_codes.append(['',''])

            # Find from_area match
            from_area_code_match = self.find_parameters_match(parameter=from_to_areas[idx][0], parameter_type='area')

            # Insert to from_to areas/codes.
            from_to_areas[idx][0] = from_area_code_match[0]
            from_to_codes[-1][0] = from_area_code_match[-1]

            # If to_area is spesified.
            if from_to_areas[idx][-1] is not None:

                # Find to_area match
                to_area_code_match = self.find_parameters_match(parameter=from_to_areas[idx][-1], parameter_type='area')
            
            # Else not spesified.
            else:
                # Set to None None.
                to_area_code_match = [None,None]

            # Insert to from_to areas/codes.
            from_to_areas[idx][-1] = to_area_code_match[0]
            from_to_codes[-1][-1] = to_area_code_match[-1]


        return datasets, from_to_areas, from_to_codes, start_end_times

    def _fill_mandatory_parameters_dict(self, d, from_to_area_code, start_end_time):
        '''Fills mandatory parameters dict with missing mandatory inputs.'''

        # Unpack areas and times.
        from_area_code = from_to_area_code[0]
        to_area_code = from_to_area_code[-1]
        start_time = start_end_time[0]
        end_time = start_end_time[-1]
        
        # Add missing parameters to mandatory parameters.
        for key, val in d.items():
            k = key.lower()

            # Insert start_time.
            if 'start' in k:
                d[key] = start_time
            elif 'date' in k:
                start_time = datetime.datetime.strptime(start_time, '%Y%m%d%H%M')
                start_time = datetime.datetime.strftime(start_time, '%Y-%m-%d')
                d[key] = start_time

            # Insert end_time.
            if 'end' in k:
                d[key] = end_time

            # Insert in_area
            if 'in_domain' in k or 'area' in k or 'connecting' in k or 'biddingzone' in k:
                d[key] = from_area_code

            # Insert out_area
            if 'out_domain' in k or 'acquiring' in k:
                d[key] = to_area_code

        # Returne filled dict.
        return d
    

    def _zipfile2df(self, zipf):
        '''Extract data from zipfile, parse all files into one df.'''
    
        # Create dataframe for storing zipfile content.
        df = pd.DataFrame()
    
        # Loop on files in zipfile.
        for filename in zipf.namelist():
        
            # Extract file xml content.
            xml_content = zipf.read(filename).decode("utf-8") 
        
            # Parse into df.
            df1 = self._response_xml_to_df(xml_content)
        
            # Append to main df.
            df = df.append(df1).reset_index(drop=True)

        # Return zipfile content in full df.
        return df
    
    def _get_entsoe_areas(self):
        '''Get entsoe areas GeoDataFrame'''
        # Retrieving entsoeapi areas GeoDataFrame
        areas = gpd.read_file("https://raw.githubusercontent.com/ocrj/entsoeapi/main/data/areas/areas.geojson")
        
        # Adding representative points to entsoe areas GeoDataFrame
        areas['coords'] = areas['geometry'].apply(lambda x: x.representative_point().coords[:])
        areas['coords'] = [coords[0] for coords in areas['coords']]

        return areas
    
    def _merge_extend_equal_rows(self, o_df, extends=['quantity', 'start', 'end']):
        '''Combines equal rows in df.'''
        
        # Create new list.
        ex = []

        # Loop on spesified extends.
        for e in extends:

            # If extend exist in o_df.columns.
            if e in o_df.columns:

                # Append it to new list.
                ex.append(e)

        # Set extends to new filtered list.
        extends = ex

        # If list is now empty.
        if len(extends) == 0:

            # Return original df.
            return o_df
        
        
        # Create new df.
        n_df = []
        o_df = o_df.reset_index(drop=True)
        # Loop on old dataframe.
        for o_idx, o_row in o_df.iterrows():
        
            # If this is first.
            if len(n_df) == 0:
            
                # Make new df of this first row in old df.
                n_df = pd.DataFrame(o_df.iloc[o_idx]).T.reset_index(drop=True)
            
            # Else not first
            else:
            
                # Set initial flag to add this row to new df.
                add_flag = True
            
                # Loop on columns in new df.
                for n_idx, n_row in n_df.iterrows():
            
                    # If all columns in old equals new, except for qxtend columns.
                    if (o_df.iloc[o_idx].drop(extends) == n_df.iloc[n_idx].drop(extends)).all():
                        # Found matching row to extend data into, reset flag to append full row.
                        add_flag = False
                    
                        # Loop on extends.
                        for exd in extends:
                        
                            # If start.
                            if 'start' in exd:
                            
                                # Unwrap if in list:
                                if isinstance(o_df.at[o_idx, exd], list):
                                    o_df.at[o_idx, exd] = o_df.at[o_idx, exd][0]
                                if isinstance(n_df.at[n_idx, exd], list):
                                    n_df.at[n_idx, exd] = n_df.at[n_idx, exd][0]
                                    
                                
                                # If extenting start is less than existing start, add as start.
                                ext_s = datetime.datetime.strptime(o_df.at[o_idx, exd], '%Y-%m-%dT%H:%MZ')
                                exi_s = datetime.datetime.strptime(n_df.at[n_idx, exd], '%Y-%m-%dT%H:%MZ')
                                if ext_s < exi_s:
                                    n_df.at[n_idx, exd] = o_df.at[o_idx, exd]
                            
                            elif 'end' in exd:

                                # Unwrap if in list:
                                if isinstance(o_df.at[o_idx, exd], list):
                                    o_df.at[o_idx, exd] = o_df.at[o_idx, exd][0]
                                if isinstance(n_df.at[n_idx, exd], list):
                                    n_df.at[n_idx, exd] = n_df.at[n_idx, exd][0]
                            
                                # If extenting end is larger than existing end, add as end
                                ext_e = datetime.datetime.strptime(o_df.at[o_idx, exd], '%Y-%m-%dT%H:%MZ')
                                exi_e = datetime.datetime.strptime(n_df.at[n_idx, exd], '%Y-%m-%dT%H:%MZ')
                                if ext_s > exi_s:
                                    n_df.at[n_idx, exd] = o_df.at[o_idx, exd]
                                
                            else:
                            
                                # Ensure cell is list
                                if isinstance(n_df.at[n_idx, exd], list) is False:
                                    n_df.at[n_idx, exd] = [n_df.at[n_idx, exd]]
                        

                                # Extend value_s to cell list.
                                n_df.at[n_idx, exd].extend(o_df.at[o_idx, exd])
                    
                        # Extended data into existing row in new df, break loop.
                        break
                
                # If not added in existing.
                if add_flag:
                    
                    # Append as new row to new df.
                    n_df = n_df.append(o_df.iloc[o_idx]).reset_index(drop=True)
                
    
        # Return merged new df.
        return n_df
    
    def find_dataset_match(self, dataset, n_matches=1, accuray_matches=0.4):
        ''' Finds closest match in avaialable api_requests, returns match.
        If no match, raise display of available api_requests.
        '''
        #fix remove spaces and set all capital letters to lower
        dataset_lower = dataset.replace(' ','_')
        dataset_lower = dataset.lower()
        datasets_list = list(self.datasets['names'])
        datasets_list_lower = [each_string.lower() for each_string in datasets_list]

        #make search for request match in available requests
        match = difflib.get_close_matches(dataset_lower, datasets_list_lower, n=n_matches, cutoff=accuray_matches)

        # if match: return single match or list of mupltiple matches, else: return None
        if len(match) == 1:
            return datasets_list[datasets_list_lower.index(match[0])]
        elif len(match) > 1:
            return match
        else:
            return None
    
    def _remap_codes2meanings(self, code, name):
        '''Remaps codes to meanings'''
    
        # Set initialy meaning as code
        meaning = code
    
        # Get list of parameters and fix.
        param_list = list(self.parameters.keys())
        param_list.pop(-1)
        param_list.append('domain')

        # Loop on list idx.
        for idx in range(len(param_list)):
        
            # If fixed param name in value name.
            if param_list[idx].lower().replace('.','').replace('_','') in name:
            
             # Get parameter type
                paratype = list(self.parameters.keys())[idx]

                # Look for remapped value.
                meaning_code = self.find_parameters_match(code, paratype)
            
                # If found, set at meaning.
                if meaning_code[0] is not None:
                    meaning = meaning_code[0]
    
        # Return meaning.
        return meaning
    
    def _response_xml_to_df(self, response, docnames=['type', 'created', 'domain'], tagsnames=['domain', 'resource', 'type', 'start', 'end', 'resolution', 'quantity', 'amount', 'name', 'voltage', 'nominalp']):
        '''Create dataframe from response'''
    
        
        # Create dataframe for storing response content.
        df = pd.DataFrame()
    
        # If input response is request.Response object.
        if isinstance(response, requests.Response):

            # Extract response content.
            response = response.content
        
        
        # Make soup
        soup = bs4.BeautifulSoup(response,'lxml')

        # Find content body tag.
        body = soup.find_all('body')[0]
    
        # If no body in response.
        if body is None:

            # Return empty df.
            return pd.DataFrame()
        
        # If bad response.
        if body.find('reason') is not None:
            if len(body.find_all('text')) > 0:
        
                # Return dataframe om reason for bad response.        
                return pd.DataFrame([body.find_all('text')[0].string], columns=['reason'])
        
        # Try to look data in document data.

        docdict = {}
        doctag = body
        # Store document data in dict.
        if doctag is not None:
            for dname in docnames:
                doctag = doctag.find_next(re.compile(dname))

                if doctag is not None:
                    docdict[doctag.name] = self._remap_codes2meanings(doctag.string, doctag.name)

        # Loop on response timeseries.
        for ts in body.find_all('timeseries'):
        
            a = docdict.copy()
            # Create new dictionary for storing timeserie content
            d = {}

            # Add dict from before timeseries.
        
            # Add timeserie contents to dictionary
            d = self._add_tags2dict(d, ts, tagsnames)
    
            for key, val in d.items():
                a[key] = val
            
            # Create df2 from dict
            df2 = pd.DataFrame([a])
        
            # Append df2 to main df.
            df = df.append(df2).reset_index(drop=True)


        
        
        # Return dataframe.
        return df

    def _seq2sets(self, start, end, quantitys=[]):
        '''
        Inputs String of start, end and measured quantitys, outputs datetimes of start, end and quantitys timestamps. 
        Input: start_str, end_str, quantitys_list
        Output: start_dt, end_dt, ts_dt
        '''
    
        # Create list for storing timestamps
        ts = []
    
        # Ensure start, end as datetime.
        start = self._datetimestr2dt(start)
        end = self._datetimestr2dt(end)            
    
        # Calculate quantitys timedeltas
        td = (end - start) / len(quantitys)
    
        # Loop on quantities to add timestamps to list.
        for idx in range(len(quantitys)):
        
            # If not first timestamp.
            if len(ts) > 0:
            
                # Append last timestamp + timedelta.
                ts.append(ts[-1] + td)
            
            # Else if first timestamp.
            else:
            
                # Append start as first timestamp.
                ts.append(start)
            
        # Return list of timestamps.
        return start, end, ts

    def _datetimestr2dt(self, timestr, dtformat='%Y-%m-%dT%H:%MZ'):
        '''If datetimestring, return as datetime.'''

        if isinstance(timestr, str):
            return datetime.datetime.strptime(timestr, dtformat)
        else:
            return timestr
    
    def _add_tags2dict(self, d, soup, tags_subnames_list):
        '''Adds tags with subnames to dict, used in response_to_df.'''
    
        # Loop on input tags_subnames_list
        for tags_subname in tags_subnames_list:
    
            # Find all tags with name containing subname
            tags = soup.find_all(re.compile(tags_subname))
    
            # Loop on tags.
            for tag in tags:
        
                # If tag has content.
                if tag.string is not None:
            
                    # If tag.name is not already in dict keys.
                    if tag.name not in d.keys():
                
                        # Add to keys with empty list
                        d[tag.name] = []
                
                    # Apply remapping
                    meaning = self._remap_codes2meanings(tag.string, tag.name)
                
                    # If measured data, allow duplicates.
                    if tag.name in ['quantity', 'position']:
                        d[tag.name].append(meaning)
                
                    # Else, append if not already in list.
                    elif tag.string not in d[tag.name]:
                        d[tag.name].append(meaning)
    
        # Return dictionary.
        return d
    
    
    #######################
    # Frontend functions ##
    #######################

    def _ensure_from_to_all(self, mandatorys_dict, from_to_codes):
        '''Adds all available areas in (from, to) and (to, from) if from is not spesified.'''

        from_to_fix = []
        
        #if isinstance(from_to_codes, str):
            #from_to_codes = [(from_to_codes, None)]
        #elif isinstance(from_to_codes, tuple):
            #from_to_codes = [from_to_codes]
        
        # If input from_to_codes is list.
        if isinstance(from_to_codes, list):

            # If first value is not list or tuple.
            if isinstance(from_to_codes[0], list) is False and isinstance(from_to_codes[0], tuple) is False:

                # Wrap all single values in list as from_area in list tuple.
                l = []
                for a in from_to_codes:
                    l.append((a, None))
                from_to_codes = l
        

        
        
        
        # Loop on mandatory parameters names.
        for m in list(mandatorys_dict.keys()):
            k = m.lower()

            # If to_area is part of mandatory parameters.
            if 'out_domain' in k or 'acquiring' in k:
                    
                # Loop on spesified from_to_codes.
                for idx in range(len(from_to_codes)):

                    # If a to_area is not spesified.
                    if from_to_codes[idx][-1] is None or len(from_to_codes[idx][-1]) == 0:

                        # Store this from_code:
                        from_code = from_to_codes[idx][0]

                        # Pop old instance
                        #from_to_codes.pop(idx-1)

                        # Get list of all available area codes.
                        all_to_codes = [x for x in list(self.parameters['Areas'].keys()) if x != from_code]

                        # Create list for storing new combinations.
                        nlist = []

                        # Extend list with all combinations of from_to and to_from.
                        nlist.extend([[from_code, x] for x in all_to_codes])
                        nlist.extend([[x, from_code] for x in all_to_codes])

                        # Insert all new combinations into main list. 
                        [from_to_codes.append(x) for x in nlist]

                    # Else (from, to) is spesified.
                    else:
                        
                        # If not (to, from) is spesified.
                        from_to = [from_to_codes[idx][-1], from_to_codes[idx][0]]
                        if from_to not in from_to_codes:

                            # Insert after (to, from) in list.
                            from_to_codes.insert((idx+1), from_to)

           # else:

        # Else not list in input:
        #else:

        # remove possible duplicates in list.
        #from_to_codes = list(dict.fromkeys(from_to_codes))
        res = []
        for i in from_to_codes:
            if i not in res:
                res.append(i)
        from_to_codes = res

        # Ensure (from, to) and (to, from)
        
        return from_to_codes


    def _request_data(self, datasets, from_to_codes, start_end_times, msg):
        '''Requesting data'''

        response = {}

        # Create dataframe for storing dataset total data response.
        df = pd.DataFrame()
        
        # Loop on datasets:
        for dataset in datasets:


            # Get requesting dataset url parameters.
            mandatorys_dict = self._get_dataset_mandatorys_dict(dataset=dataset)
        
            # If out_area is part of mandatory parameters but is missing in a spesified from_to_codes:
            # Adds (from, to) and (to, from) for that are to all available areas.
            from_to_codes_fix = self._ensure_from_to_all(mandatorys_dict, from_to_codes)

            

            # Loop on from_to_areas_list
            for from_to_code in from_to_codes_fix:


                # Assume start_end_time is ok.
                bad_start_end_flag = True
                w = 0
                while bad_start_end_flag and w < 2:
                    w += 1

                
                    # Loop on start_end_times_list.
                    for start_end_time in start_end_times:

                        # While not error in response:
                    
                        if 'print' in msg:
                            # Making request
                            print('\n********************************')
                            print('REQUEST:')
                            print(f'dataset = "{dataset}"')
                            print(f'from_to = {from_to_code}')
                            print(f'start_end = {start_end_time}')
                        
        
                        parameters_dict = self._fill_mandatory_parameters_dict(mandatorys_dict, from_to_code, start_end_time)


                        response, url = self._call_api(parameters_dict=parameters_dict)

                        if 'url' in msg:
                                print(f'url = {url}')
                    
                    
                        # Try if response is zipfile.
                        zipfileflag = False
                        try:
                            # Create zipfile.
                            zipf = zipfile.ZipFile(io.BytesIO(response.content))

                            # If try success, set zipfile flag true.
                            zipfileflag = True
                        
                            # Parse content in zipfile into df.
                            df1 = self._zipfile2df(zipf)

                            # Add dataset name to response.
                            df1.insert(0, 'dataset', dataset)
                            df1.insert(1, 'success', True)
                            df1.insert(2, 'parameters', str(parameters_dict))
                            if 'reason' not in df1.columns:
                                df1.insert(3, 'reason', '')
                        
                        # Except error if not zipfile.
                        except (zipfile.BadZipFile):
                            None
        
                        # If bad response with reason text.
                        if 'text' in response.text and not zipfileflag:
                            reason_str = bs4.BeautifulSoup(response.content, 'lxml').find('text').string
                        
                            # Print msg.
                            if 'print' in msg:
                                print("RESPONSE:")
                                #print('status = ERROR, bad request.')
                                print(f'reason = {reason_str}')
                                #print(f'url = {url}')

                                
                                # If spesified query days max in reason.
                                if 'allowed: ' in reason_str:
                                    val_unit = reason_str.split('allowed: ')[-1].split(',')[0].split(' ')
                                    print(f'ALLOWED: {val_unit[0]} in unit {val_unit[-1]}')

                                    start = datetime.datetime.strptime(start_end_time[0], '%Y%m%d%H%M')
                                    end = datetime.datetime.strptime(start_end_time[-1], '%Y%m%d%H%M')

                                    new_start_end = []
                                    while start < end:

                                        start_str = start.strftime('%Y%m%d%H%M')

                                        start = start+datetime.timedelta(days=1)

                                        end_str = (start).strftime('%Y%m%d%H%M')

                                        new_start_end.append((start_str, end_str))

                                    start_end_times = new_start_end




                                    break
                                else:
                                    bad_start_end_flag = False

                            # Try to fix new request from bad response reason.
                            fix_msg = self._reason_fix_request(reason_str) #TODO: not implemented.


                            # Add dataset name and reason to parameters_dict
                            d = {}
                            d['dataset'] = dataset
                            d['success'] = False
                            d['parameters'] = str(parameters_dict)
                            d['reason'] = reason_str


                            # Make this the bad response dataframe.
                            df1 = pd.DataFrame([d])

                        # Else good response.
                        elif not zipfileflag:

                            # Create dataframe from this response.
                            df1 = self._response_xml_to_df(response)

                            # Add dataset name to response.
                            df1.insert(0, 'dataset', dataset)
                            df1.insert(1, 'success', True)
                            df1.insert(2, 'parameters', str(parameters_dict))
                            if 'reason' not in df1.columns:
                                df1.insert(3, 'reason', '')


                        if 'print' in msg:
                            print('**********************************')

                        # Append this dataframe response dataframe to total dataframe.
                        df = df.append(df1).reset_index(drop=True)
        

        # Return requested data.
        return df
    

    def set_apikey(self, api_key):
        '''Setting entsoe-t api_key'''
        self.api_key = api_key

    def get_data(self, dataset, from_to, start_end=None, msg=['print']):
        '''
        Main frontend function for getting data from Entsoe-t platform.
        
        :Inputs:
            -dataset: Name of dataset. Name is "close-matched" against list of available datasets in .datasets['names']
            -from_to: ('from_area', 'to_area') in request. "Close-matched" against available areas in .parameters['Areas']
            -start_stop: ('start_time','end_time') "format=yyyyddmmHHMM" in request.
        
        :Outputs:
            -df: Response content in pandas.DataFrame.

        :Info:
            -

        '''

        # Check if api_key is missing.
        if self.api_key is None:

            # Print msg.
            print('ERROR: api_key is missing. Set api_key as input to module or by function .set_apikey(api_key).')
            
            # Return None
            return None
        
        # Finds dataset match in datasets, area match in parameters and fix time formats.
        datasets_fix, from_to_areas_fix, from_to_codes_fix, start_end_times_fix = self._fix_get_inputs(dataset, from_to, start_end)

        
        # Loop on matched datasets.
        for dset in datasets_fix:

            # If a dataset is None.
            if dset is None:

                # Print errormsg.
                print(f'ERROR:\n No matching datasets found for input "{dset}"')

                # Return None.
                return None

        
        # Requesting data.
        df = self._request_data(datasets_fix, from_to_codes_fix, start_end_times_fix, msg=msg)


        # Create dataframe for storing fixed df response.
        df_fix = pd.DataFrame()

        # Combine all bad_responses into one row in dataframe.
        bad_df = df[df['reason'].apply(lambda x: len(str(x)) != 0)]

        # If there was any bad responses.
        if len(bad_df) > 0:

            # Append as first row to df_fixed
            bad_d = {}
            bad_d['dataset'] = bad_df['dataset'].values.tolist()
            bad_d['success'] = bad_df['success'].values.tolist()
            bad_d['parameters'] = bad_df['parameters'].values.tolist()
            bad_d['reason'] = bad_df['reason'].values.tolist()
            df_fix = df_fix.append(pd.DataFrame([bad_d])).reset_index(drop=True)
        
        # Extract good responses.
        good_df = df[df['reason'].apply(lambda x: len(str(x)) == 0)]

        # Combine rows 'quantity', 'start' and 'end' if rest is equal.
        good_df_fix = self._merge_extend_equal_rows(good_df, extends=['parameters', 'createddatetime', 'quantity', 'start', 'end'])
        
        # Append good_df to fixed df.
        df_fix = df_fix.append(good_df_fix).reset_index(drop=True)

        # Unpack single values wrapped in lists.
        for col in df_fix.columns:
            df_fix[col] = [x[0] if isinstance(x,list) and len(x) == 1 else x for x in df_fix[col]]

        # Fix timestring to datetime and add timestamps
        if 'start' in df_fix.columns and 'end' in df_fix.columns and 'quantity' in df_fix.columns:
            df_fix['timestamp'] = ''
            for idx, row in df_fix.iterrows():

                # If quantity is not np.na
                try:
                    if isinstance(df_fix.at[idx, 'quantity'], list) or isinstance(df_fix.at[idx, 'quantity'], int):
                        start, end, df_fix.at[idx, 'timestamp'] = self._seq2sets(df_fix.at[idx, 'start'], df_fix.at[idx, 'end'], df_fix.at[idx, 'quantity'])
                except(ValueError, TypeError):
                    None
        
        # Return fixed df.
        return df_fix
        
    def get_areas(self):
        '''Returns available areas as GeoDataFrame.'''
        
        # Get available areas from api statics.
        codes = self.parameters['Areas'].keys()
        names = self.parameters['Areas'].values()
        df = pd.DataFrame(zip(codes, names), columns=['Code', 'Meaning'])

        # Merge available api areas and available areas geometries.
        gdf = self.areas
        for idx in df.index:
            if df.at[idx, 'Meaning'] not in gdf['Meaning'].tolist():
                gdf = gdf.append(df.iloc[idx])

        # Return available api areas as GeoDataFrame.
        return gdf
    
    def show_client_summary(self):
        '''Create and printout client features summary in table.'''

        print("-Available API Parameters-")
        for _type, _param in self.parameters.items():
            print(f"\n{_type}")
            print(json.dumps(_param, indent=2, default=str))
        return None
    

    #####################
    # Inner functions
    #####################


    def _make_statics_guide_toc_df(self, statics_soup):

        # Extract toc and toc title.
        toc = statics_soup.find(id="toc")
        
        # Create DataFrame for storing toc.
        df = pd.DataFrame([], columns=["sectlevel1", "sectlevel2"])
        
        # Get sectlevel1 elements.
        sectlevel1 = toc.find(class_="sectlevel1")
        
        # Loop on the elements.
        for sectlevel1 in sectlevel1.children:

            # Store level name string.
            sectlevel1_name = str(sectlevel1.find("a").string)
            
            # Find sectlevel2 in this sectlevel1.
            sectlevel2 = sectlevel1.find(class_="sectlevel2")

            # If sectlevel2 is not empty.
            if sectlevel2 is not None:

                # Loop on sectlevel2 elements.
                for sectlevel2_name in sectlevel2.find_all("a"):

                    # Append combination of sectlevel1 and sectlevel2 to DataFrame.
                    df = df.append({'sectlevel1': str(sectlevel1_name), 'sectlevel2': str(sectlevel2_name.string)}, ignore_index=True)

            # If sectlevel2 is empty.
            else:
                
                # Append combination of sectlevel1 for both locations levelcolumns in DataFrame.
                df = df.append({'sectlevel1': str(sectlevel1_name), 'sectlevel2': str(sectlevel1_name)}, ignore_index=True)

        return df
    

    def _find_parameters_type_match(self, parameter_type, n_matches=1, accuracy_matches=0.4):
        ''' Finds closest match in available parameters types.
        '''
        #fix remove spaces and set all capital letters to lower
        parameter_type_lower = parameter_type.replace(' ','_')
        parameter_type_lower = parameter_type.lower()
        parameter_type_list = list(self.parameters.keys())
        parameter_type_list_lower = [each_string.lower() for each_string in parameter_type_list]

        #make search for request match in available parameter types
        match = difflib.get_close_matches(parameter_type_lower, parameter_type_list_lower, n=n_matches, cutoff=accuracy_matches)

        # if match: return single match or list of multiple matches, else: return None
        if len(match) == 1:
            return parameter_type_list[parameter_type_list_lower.index(match[0])] #return match from original list
        elif len(match) > 1:
            return match
        else:
            return None

    def find_parameters_match(self, parameter, parameter_type, n_matches=1, accuracy_matches=0.9):
        ''' 
        Finds closest match in available parameters.

        Input: parameter, parameter_type
        Output: matched_parameter_value, matched_parameter_code

        '''
        
        # Initially search for match on existance of spesified parameter type in entsoeapi.
        parameter_type_match = self._find_parameters_type_match(parameter_type=parameter_type)
        
        # If not found match on spesified parameter type.
        if parameter_type_match is None:

            # Return None.
            return None, None
        
        # Fix searchstring with removed spaces and all lowered letters.
        parameter_lower = parameter.replace(' ','_')
        parameter_lower = parameter.lower()
        
        # Store list of available parameter values in original and lowered form.
        parameter_values_list = list(self.parameters[parameter_type_match].values())
        parameter_values_list_lower = [each_string.lower() for each_string in parameter_values_list]
        
        # Store list of available parameter codes in original and lowered form.
        parameter_keys_list = list(self.parameters[parameter_type_match].keys())
        parameter_keys_list_lower = [each_string.lower() for each_string in parameter_keys_list]

        # Make search for match in parameter_values:
        match = difflib.get_close_matches(parameter_lower, parameter_values_list_lower, n=n_matches, cutoff=accuracy_matches)
        
        # If not loose match on string, check if whole parameter word in string
        # If not match in full string search.
        if len(match) < 1:

            # Loop on available parameters list,
            match = []
            for c in range(len(parameter_values_list_lower)):
                
                # Fix and split parameter values into list of substrings.
                b = parameter_values_list_lower[c].replace(",","")
                b = b.split(" ")

                # Search for match in list of parameter substrings.
                if parameter_lower in b:
                    
                    # If match is found, add to matchlist.
                    match.append(parameter_values_list_lower[c])
        
        # If match is found in parameter type values.
        if len(match) == 1:

            # Return matched value and code and parametertype.
            value = parameter_values_list[parameter_values_list_lower.index(match[0])]
            code = parameter_keys_list[parameter_values_list_lower.index(match[0])]
            return value, code
        
        # If not found match in values, search for match in keys:
        match = difflib.get_close_matches(parameter_lower, parameter_keys_list_lower, n=n_matches, cutoff=accuracy_matches)
            
        # If match is found in parameter type codes.
        if len(match) == 1:

            # Return matched value and code and parametertype
            value = parameter_values_list[parameter_keys_list_lower.index(match[0])]
            code = parameter_keys_list[parameter_keys_list_lower.index(match[0])]
            return value, code 

        # If no match found in either parameter type values or codes
        else:

            # Return None
            return None, None




#####################
# Main functions
#####################

def main():
    '''Main'''
    pass


if __name__ == "__main__":
    print("You called entsoeapi.py as __main__.")
    #client = EntsoeTransparencyClient(api_key=Tr)
    
    #client.get_entsoe_statics_guide()
    #client.show_parameters()

    #client._get_entsoe_api_statics()

    #r = requests.get('https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html')

    #soup = bs4.BeautifulSoup(r.content)
    #print(soup.prettify())
    

