
def save_dict_to_csv(d, filepath=''):
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



