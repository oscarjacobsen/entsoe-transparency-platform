#!/usr/bin/env python


# Script for getting api statics from Api User Guide 
# url = https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html


import requests
import bs4
import pandas as pd
import re


def get_api_statics(savepath = '',guide_url='https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html'):
    '''Webscraper for Entso-E Transparency Platform api guide'''

    # Request guide html content from url.
    response = requests.get(guide_url)

    # Create BeautifulSoup object, go to content tag.
    content_soup = bs4.BeautifulSoup(response.text, "lxml").find(id="static-content").find(id="content")
    
        
    # Finding all headers. TODO: missing 1.4. Parameters due du it being nested in ulist. Content included in 1.3.
    headers = content_soup.find_all(lambda x: x.name in ['h2', 'h3', 'h4'] and len(x.string) > 2)
        
    # Extract content in guide chapters and appendix.
    soup_chapters = content_soup.find_all(class_="sect1")
    #soup_ch1_ch2 = soup_chapters[:1] #incl: api_url, 
    #soup_ch3 = soup_chapters[2]
    soup_ch4 = soup_chapters[3] #incl: possible requests with parameterspesifications and request structure examples.
    soup_apndxA = soup_chapters[4] #incl: parameterslists,
    #soup_apndxB = soup_chapters[5]

        
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
                

    return datasets, parameters




######################################################################
def __save_dict_to_csv(d, filepath=''):
    '''Saving dictionary to file as .csv'''
    # load csv module
    import csv

    # define a dictionary with key value pairs
    d = {'Python' : '.py', 'C++' : '.cpp', 'Java' : '.java'}

    # open file for writing, "w" is writing
    w = csv.writer(open(filepath, "w"))

    # loop over dictionary keys and values
    for key, val in d.items():

        # write every key and value to file
        w.writerow([key, val])



def main():
    '''Executable script main function.'''
    import sys

    get_api_statics()



# If module is execudes as executable script, run main.
if __name__ == "__main__": 

    main()
