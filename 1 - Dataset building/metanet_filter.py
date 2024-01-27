import json
import csv
import requests
import time

# MetaNet Filter:
# - input: MetaNet conceptual metaphors and frames scraped from website
# - output: MetaNet conceptual metaphor corpus with both source and target found in conceptnet

# For each conceptual metaphor m, the representation of src and tgt is selected with the following priority:
# 1) src/tgt frame of m
# 2) breadth-first search of "both source and target subcase of" and "src/tgt subcase of" related metaphors' src/tgt frames
# 3) breadth-first search of “is subcase of” related frames, starting from src/tgt frames of m
# 4) breadth-first search of “is subcase of” related frames, starting from the metaphors of which m is a subcase
# 5) derive src/tgt from m's name, assuming that it has the form "TARGET [BE] SOURCE"
# 6) rule 5) applied to the metaphors of which m is a subcase


REQ_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0',
'Accept': 'application/json'}

# save locally concepts already looked for in ConceptNet to reduce API calls
conceptnet_cache = dict()

# returns True iff concept is a hit on ConceptNet
def is_in_conceptnet(concept):
    if concept is None:
        return False
    if concept not in conceptnet_cache.keys():
        #print(f"Looking for {concept} in ConceptNet...")
        query = f"https://api.conceptnet.io/c/en/{concept.strip().lower().replace(" ", "_").replace("-", "_")}"

        json = None
        limit = 10  #max n of retries
        delay = 1   #n of seconds to wait between retries
        retried = 0
        got_it = False

        # if the response is not a json or is a json with error != 404, waits and retries
        while not got_it and retried < limit:
            try:
                json = requests.get(query, REQ_HEADERS).json()
                if "error" in json.keys() and json["error"]["status"] != 404:
                    got_it = False
                    retried += 1
                    print(f'>>>>WARNING: failed attempt {retried}/{limit}')
                    time.sleep(delay)
                else:
                    got_it = True
            except:
                got_it = False
                retried += 1
                print(f'>>>>WARNING: failed attempt {retried}/{limit}')
                time.sleep(delay)
        
        if "error" in json.keys():
            conceptnet_cache[concept] = False
        else:
            conceptnet_cache[concept] = True
    
    return conceptnet_cache[concept]
    
# rel_dict describes a relation's graph as an adjacency list.
# This function expands the list of each node.
# This is the same as materialising the transitivity of the relationship expressed by rel_dict. 
def relation_breadth_first_expansion(rel_dict):
    # for each key
    for key in rel_dict.keys():
        # build a FIFO queue
        # add each node in the main value list to the queue
        queue = list(rel_dict[key])

        # while the queue is not void
        while len(queue) > 0:
            # n = first node in the queue
            # remove n from the queue
            n = queue.pop(0)

            # ignore metaphors not present in MetaNet
            if n in rel_dict.keys():
                # if n is not in the main value list, add it to the value list
                if n not in (rel_dict[key]):
                    rel_dict[key].append(n)

                # for each metaphor in the value list of n
                for other_node in rel_dict[n]:
                    # add it to the queue
                    queue.append(other_node)

# auxiliary function to split the name of the conceptual metaphor around the verb TO BE,
# assuming that the conceptual metaphor name is called TARGET [BE] SOURCE
def split_conceptual_metaphor(metaphor):
    splitters = [" are the ", " are an ", " are a ", " are ",
                  " is the ",  " is an ",  " is a ",  " is "]
    # case-insensitive search (not all conceptual metaphor names are uppercase)
    metaphor = metaphor.lower()
    for be in splitters:
        # split the name on the first applicable splitter
        if be in metaphor:
            metaphor = metaphor.split(be)
            return (metaphor[0].strip(), metaphor[1].strip())



def main():

    ###########################################
    # Read metanet_classes and metanet_frames #
    ###########################################

    # save source and target of each metaphor in a dictionary
    metaphors_dict = dict()
    # save "source subcase of" and "target subcase of" relations in two dictionaries
    super_tgt_of = dict()
    super_src_of = dict()

    with open("metanet_classes.jsonl", encoding="utf-8") as scraped_data:
        for line in scraped_data:
            scraped = json.loads(line.strip())
            
            metaphor = scraped["metaphor"]
            src = scraped["source frame"]
            tgt = scraped["target frame"]

            metaphors_dict[metaphor] = {"source": src, "target": tgt}

            super_st = scraped["both s and t subcase of"]

            super_source = scraped["source subcase of"]
            super_src_of[metaphor] = super_st + super_source

            super_target = scraped["target subcase of"]
            super_tgt_of[metaphor] = super_st + super_target

    # save "subcase of" frame relation in a dictionary
    super_frames_of = dict()

    with open("metanet_frames.jsonl", encoding="utf-8") as scraped_data:
        for line in scraped_data:
            scraped = json.loads(line.strip())
            
            frame = scraped["frame"]
            super_frames = scraped["subcase of"]
            super_frames_of[frame] = super_frames

    # extend the value lists of the subcase dictionaries with a breadth-first search of the relation
    relation_breadth_first_expansion(super_src_of)
    relation_breadth_first_expansion(super_tgt_of)
    relation_breadth_first_expansion(super_frames_of)
    
    ###############################################
    # build MetaNet corpus using the dictionaries #
    ###############################################
    with open("metanet_corpus.tsv", "w", encoding='utf-8', newline="") as  tsvfile:
        output_writer = csv.writer(tsvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        output_writer.writerow(["#Source", "#Target", "#ConceptualMetaphor"])

        lost_count = 0
        too_generalized_count = 0

        # for each conceptual metaphor in MetaNet
        for met in metaphors_dict.keys():

            ###################################
            # SOURCE - PRIORITY RULES 1 and 2 #
            ###################################

            source_frame = metaphors_dict[met]["source"]

            # check for subsumer in "source subcase of" relation
            met_subsumers_list = list(super_src_of[met])
            
            # while the source frame is not in ConceptNet and there is a subsumer
            while not is_in_conceptnet(source_frame) \
                        and len(met_subsumers_list) > 0:
                # retrieve subsumer
                subsumer_met = met_subsumers_list.pop(0)
                # replace source frame with the subsumer's source frame (if exists)
                if subsumer_met in metaphors_dict.keys():
                    source_frame = metaphors_dict[subsumer_met]["source"]

            ###################################
            # SOURCE - PRIORITY RULES 3 and 4 #
            ###################################
                    
            met_subsumers_list = [met] + list(super_src_of[met])

            # explore frame relations starting from met's source frame
            while not is_in_conceptnet(source_frame) \
                        and len(met_subsumers_list) > 0:
                cur_met = met_subsumers_list.pop(0)
                # check that cur_met is represented in MetaNet
                if cur_met in metaphors_dict.keys():
                    source_frame = metaphors_dict[cur_met]["source"]

                    if source_frame in super_frames_of.keys():
                        frame_subsumers_list = list(super_frames_of[source_frame])
                        while not is_in_conceptnet(source_frame) \
                                    and len(frame_subsumers_list) > 0:
                            # replace source frame with super-frame
                            source_frame = frame_subsumers_list.pop(0)
            
            ###################################
            # SOURCE - PRIORITY RULES 5 and 6 #
            ###################################
                    
            met_subsumers_list = [met] + list(super_src_of[met])

            # try to infer the source from metaphor's name, assuming that it has the form TARGET [BE] SOURCE
            # starting from met and following metaphors "subcase of" relations
            while not is_in_conceptnet(source_frame) \
                        and len(met_subsumers_list) > 0:
                cur_met = met_subsumers_list.pop(0)
                source_frame = split_conceptual_metaphor(cur_met)[1]
            

            ###################################
            # TARGET - PRIORITY RULES 1 and 2 #
            ###################################
                        
            target_frame = metaphors_dict[met]["target"]
                    
            # check for subsumer in "target subcase of" relation
            met_subsumers_list = list(super_tgt_of[met])
            
            # while the target frame is not in ConceptNet and there is a subsumer
            while not is_in_conceptnet(target_frame) \
                        and len(met_subsumers_list) > 0:
                # retrieve subsumer
                subsumer_met = met_subsumers_list.pop(0)
                # replace target frame with the subsumer's target frame (if exists)
                if subsumer_met in metaphors_dict.keys():
                    target_frame = metaphors_dict[subsumer_met]["target"]

            ###################################
            # TARGET - PRIORITY RULES 3 and 4 #
            ###################################
                    
            met_subsumers_list = [met] + list(super_tgt_of[met])

            # explore frame relations starting from met's target frame
            while not is_in_conceptnet(target_frame) \
                        and len(met_subsumers_list) > 0:
                cur_met = met_subsumers_list.pop(0)
                # check that cur_met is represented in MetaNet
                if cur_met in metaphors_dict.keys():
                    target_frame = metaphors_dict[cur_met]["target"]

                    if target_frame in super_frames_of.keys():
                        frame_subsumers_list = list(super_frames_of[target_frame])
                        while not is_in_conceptnet(target_frame) \
                                    and len(frame_subsumers_list) > 0:
                            # replace target frame with super-frame
                            target_frame = frame_subsumers_list.pop(0)
            
            ###################################
            # TARGET - PRIORITY RULES 5 and 6 #
            ###################################
                    
            met_subsumers_list = [met] + list(super_src_of[met])

            # try to infer the target from metaphor's name, assuming that it has the form TARGET [BE] SOURCE
            # starting from met and following metaphors "subcase of" relations
            while not is_in_conceptnet(target_frame) \
                        and len(met_subsumers_list) > 0:
                cur_met = met_subsumers_list.pop(0)
                target_frame = split_conceptual_metaphor(cur_met)[0]
                
            
            ###############################
            # OUTPUT FOR CURRENT METAPHOR #
            ###############################
                    
            # if both source and target frame are represented in ConceptNet
            if is_in_conceptnet(source_frame) and is_in_conceptnet(target_frame):
                # if source and target frame are different
                if source_frame != target_frame:
                    output_writer.writerow([source_frame, target_frame, met])
                # else the generalization made the two concepts collide: print a warning
                else:
                    lost_count += 1
                    too_generalized_count += 1
                    print(f"Conceptual Metaphor {met} cannot be represented")
                    print(f"\t> source frame \"{metaphors_dict[met]["source"]}\" and target frame \"{metaphors_dict[met]["target"]}\" were both generalized as \"{source_frame}\"")
                    print()

            # else print a warning
            else:
                lost_count += 1
                print(f"Conceptual Metaphor {met} cannot be represented")
                if not is_in_conceptnet(source_frame):
                    print(f"\t> source frame \"{metaphors_dict[met]["source"]}\" and subsumers not found in ConceptNet")
                if not is_in_conceptnet(target_frame):
                    print(f"\t> target frame \"{metaphors_dict[met]["target"]}\" and subsumers not found in ConceptNet")
                print()

        print(lost_count, "conceptual metaphors not representable")




if __name__ == '__main__': main()



