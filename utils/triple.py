from utils.wikidata import wiki_entity_label, wiki_predicate_label, general_wiki_search
import ast



class triple(object):
    def __init__(self, values, types, kg='wiki'):
        self.values = values
        self.types = types
        self.kg = kg
        self._get_labels()

    def _get_labels(self):
        self.labels = []
        if self.kg == 'wiki':

            self.labels.append(self._single_label(self.values[0], self.types[0], is_entity=True))
            self.labels.append(self._single_label(self.values[1], self.types[1], is_entity=False))
            self.labels.append(self._single_label(self.values[2], self.types[2], is_entity=True))

    def _single_label(self, value, type, is_entity):
        #num_var = 0
        if type == 'NamedNode':
            if is_entity:
                label = wiki_entity_label(value)
            else:
                label = wiki_predicate_label(value)
        elif type == 'Variable' or 'Literal':
            #num_var = 1
            label = value

        else:
            print("Type invalid")
            return None

        return label #num_var
    
    def to_NL(self, model):
        if_var = [1 if s == 'Variable' else 0 for s in self.types]
        num_var = sum(if_var)


        if num_var == 0:
            return model(self.labels, has_var = False)
        
        elif num_var == 1:

            if if_var[0] == 1:
                input = ['var1', self.labels[1], self.labels[2]]
                sentence = model(input, has_var = True, var_pos = 0)
                sentence = sentence.replace('var1', '?'+self.labels[0])
                

            elif if_var[1] == 1:
                input = [self.labels[0], 'var1', self.labels[2]]
                sentence = model(input, has_var = True, var_pos = 1)
                sentence = sentence.replace('var1', '?'+self.labels[1])

            else:
                input = [self.labels[0], self.labels[1],'var1']
                sentence = model(input, has_var = True, var_pos = 2)
                sentence = sentence.replace('var1', '?'+self.labels[2])

            return sentence
        
        elif num_var == 2:
            if if_var[1] == 0:
                input = ['var1', self.labels[1], 'var2']
                sentence = model(input, has_var = True, var_pos = 13)
                sentence = sentence.replace('var1', '?'+self.labels[0])
                sentence = sentence.replace('var2', '?'+self.labels[2])
                return sentence

            else:
                if if_var[0] == 0:

                    sentence = self.labels[0] + ' has relation ?' + self.labels[1] + ' to the variable ?' + self.labels[2]


                else:
                    if self.types[2] == 'NamedNode':
                        sentence = 'The variable ?' + self.labels[0] + ' has relation ?' + self.labels[1] + " to " + self.labels[2]
                    elif self.types[2] == 'Literal': 
                        sentence = 'The variable ?' + self.labels[0] + ' has property ?' + self.labels[1] + " with value as " + self.labels[2]
                    else:
                        print('not supported var=2 case')
                return sentence

        else:
            return 'The variable ?' + self.labels[0] + ' has relation ?' + self.labels[1] + ' to the variable ?' + self.labels[2]
        
def single_triple2NL(single_seg, model, kg ='wiki'):
    print(single_seg)
    values = [single_seg['subject']['value'], single_seg['predicate']['value'], single_seg['object']['value']]
    types = [single_seg['subject']['termType'], single_seg['predicate']['termType'], single_seg['object']['termType']]

    t = triple(values, types, kg=kg)
    nl_expression = t.to_NL(model)

    return t, nl_expression

def bgp2NL_parsed(data, model, kg = 'wiki'):
    res = []
    triples = []
    assert(data['where'][0]['type'] == 'bgp')
    bgps = data['where'][0]['triples']
    for tp in bgps:

        t, nl = single_triple2NL(tp, kg = kg, model = model)
        res.append(nl)
        triples.append(t)
    
    return res, triples
        
def bgp2NL(data, model, kg = 'wiki'):
    res = []
    triples = []
    assert(data['type'] == 'bgp')
    bgps = data['triples']
    for tp in bgps:

        t, nl = single_triple2NL(tp, kg = kg, model = model)
        res.append(nl)
        triples.append(t)
    
    return res, triples


def nl2bgp_eval(bgp_pairs, model, topk=10):
	res = []
	for i in range(len(bgp_pairs[0])):
		if topk is not None and i > topk:
			return res

		print(bgp_pairs[0][i])
		gen_tp_str = model(bgp_pairs[0][i])
		gen_tp = ast.literal_eval(gen_tp_str)

		print(gen_tp)

		# search
		sub = general_wiki_search(gen_tp[0])
		pred = general_wiki_search(gen_tp[1], is_entity=False)
		obj = general_wiki_search(gen_tp[2])

		print('Subject:  \n')
		print(sub)
		print(bgp_pairs[1][i].values[0])
		print(bgp_pairs[1][i].labels[0])

		print('\n')
		print('Predicate:  \n')
		print(pred)
		print(bgp_pairs[1][i].values[1])
		print(bgp_pairs[1][i].labels[1])

		print('\n')
		print('Object:  \n')
		print(obj)
		print(bgp_pairs[1][i].values[2])
		print(bgp_pairs[1][i].labels[2])
		
		print('\n\n')