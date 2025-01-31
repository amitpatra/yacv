import logging
import pandas as pd
from pprint import pprint
from copy import deepcopy
from collections import OrderedDict
from yacv.grammar import Grammar, first
from yacv.abstractsyntaxtree import AbstractSyntaxTree
from yacv.utils import YACVError
from yacv.constants import *
class LRItem(object):
    def __init__(self, production=None, dot_pos=0, lookaheads=[]):
        self.production = production
        self.dot_pos = dot_pos
        self.lookaheads = lookaheads
        self.update_reduce()

    def update_reduce(self):
        if self.dot_pos == len(self.production.rhs) \
        or self.production.rhs[self.dot_pos] in ['$', YACV_EPSILON]:
            self.reduce = True
        else:
            self.reduce = False

    def __str__(self):
        # TODO: Some string format customization maybe ?
        lhs, rhs = self.production.lhs, self.production.rhs
        lookaheads = sorted(self.lookaheads)
        dot_pos = self.dot_pos
        ret = '{} -> {}{}{}'.format(
                lhs,
                ''.join(rhs[:dot_pos]) if dot_pos > 0 else '',
                YACV_DOT,
                ''.join(rhs[dot_pos:])
                )
        if lookaheads:
            ret += ', {}'.format('/'.join(lookaheads))
        return ret

    def __repr__(self):
        return '< ' + str(self) + ' > at {}'.format(hex(id(self)))
    
    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return not self == other

class LRAutomatonState(object):
    def __init__(self, items=[], preferred_action='S'):
        self.items = items
        self.preferred_action = preferred_action
        self.shift_items = []
        self.reduce_items = []
        self.accept = False # is accepting state ?
        self.update_shift_reduce_items()
        self.update_conflicts()

    def update_shift_reduce_items(self):
        for i, item in enumerate(self.items):
            item.update_reduce()
            if item.reduce:
                self.reduce_items.append(i)
                if item.production.rhs[-1] == '$':
                    self.accept = True
            else:
                self.shift_items.append(i)

    def update_conflicts(self):
        if len(self.reduce_items) > 1:
            # Reduce Reduce conflict
            self.rr = True
            self.conflict = True
        if len(self.reduce_items) > 1 and len(self.shift_items) > 1:
            # Shift Reduce conflict
            self.sr = True
            self.conflict = True

    def __str__(self, join_on='\n'):
        # TODO: Can provide some customization here
        return join_on.join([str(item) for item in self.items])

    def __repr__(self):
        return '< LRAutomatonState with items: ' + str(self) + \
                ' > at {}'.format(hex(id(self)))

    def __eq__(self, other):
        return self.items == other.items

    def __ne__(self, other):
        return not self == other

class LRParser(object):
    def __init__(self, fname='another-grammar.txt'):
        self.grammar = Grammar(fname)
        self.is_valid = True
        self.automaton_states = []
        self.automaton_transitions = OrderedDict()
        self.automaton_built = False
        self.build_automaton()
        tuples = [(YACV_ACTION, symbol) for symbol in self.grammar.terminals] + \
            [(YACV_GOTO, symbol) for symbol in self.grammar.nonterminals.keys()]
        columns = pd.MultiIndex.from_tuples([('', x[0])
            if pd.isnull(x[1]) else x for x in tuples])
        self.parsing_table = pd.DataFrame(
            columns = columns,
            index = self.automaton_transitions.keys()
        )
        self.parsing_table.loc[:,:] = YACV_ERROR
        self.parsing_table_built = False
        self.build_parsing_table()

    def closure(self, i):
        log = logging.getLogger('yacv')
        queue = i if isinstance(i, list) else [i]
        ret = []
        log.debug('Computing closure of {}'.format(queue))
        while queue:
            item = queue.pop(0)
            assert isinstance(item, LRItem)
            ret.append(item)
            log.debug('item = {}, reduce = {}'.format(item, item.reduce))
            if item.reduce:
                continue
            next_symbol = item.production.rhs[item.dot_pos]
            log.debug('next_symbol = {}'.format(next_symbol))
            if next_symbol == YACV_EPSILON \
            or next_symbol in self.grammar.terminals:
                continue
            prod_ids = self.grammar.nonterminals[next_symbol]['prods_lhs']
            log.debug('new_prod_ids = {}'.format(prod_ids))
            for prod_id in prod_ids:
                prod = self.grammar.prods[prod_id]
                log.debug(type(item.lookaheads))
                if item.lookaheads:
                    f = first(self.grammar, 
                            item.production.rhs[item.dot_pos+1:])
                    if not f or YACV_EPSILON in f:
                        f = f.union(set(item.lookaheads))
                    f = f.difference([YACV_EPSILON])
                else:
                    f = []
                new_item = LRItem(prod, 0, f)
                log.debug('new_item = {}'.format(new_item))
                if new_item not in queue and new_item not in ret:
                    queue.append(new_item)
        kernel_lookaheads = OrderedDict()
        for item in ret:
            kernel = LRItem(item.production, item.dot_pos)
            key = str(kernel)
            if key not in kernel_lookaheads.keys():
                kernel_lookaheads[key] = {
                    'kernel': kernel,
                    'lookaheads': []
                }
            curr = kernel_lookaheads[key]['lookaheads']
            curr = sorted(list(set(curr).union(item.lookaheads)))
            kernel_lookaheads[key]['lookaheads'] = curr
        ret = []
        for key, val in kernel_lookaheads.items():
            kernel, lookaheads = val['kernel'], val['lookaheads']
            item = LRItem(kernel.production, kernel.dot_pos, lookaheads)
            ret.append(item)
        return ret

    def build_automaton_from_init(self, init):
        log = logging.getLogger('yacv')
        if self.automaton_built:
            log.warn('Automaton is already built!')
            return
        self.automaton_states.append(init)
        self.automaton_transitions[0] = OrderedDict()
        visited_states = []
        to_visit = [init]
        while to_visit:
            curr = to_visit.pop(0)
            curr_idx = self.automaton_states.index(curr)
            log.debug('curr = {}'.format(curr))
            visited_states.append(curr)
            tmp_items = deepcopy(curr.items)
            next_symbols = OrderedDict()
            for item in tmp_items:
                if item.reduce:
                    continue
                key = item.production.rhs[item.dot_pos]
                if key not in next_symbols.keys():
                    next_symbols[key] = []
                item.dot_pos += 1
                item.update_reduce()
                next_symbols[key].append(item)
            for key, items in next_symbols.items():
                next_state = LRAutomatonState(self.closure(items))
                log.debug(next_state)
                if next_state not in self.automaton_states:
                    # Is next_state completely new ?
                    log.debug('Adding new state {}'.format(next_state))
                    self.automaton_states.append(next_state)
                    self.automaton_transitions[len(self.automaton_states)-1] = \
                        OrderedDict()
                    to_visit.append(next_state)
                elif next_state not in visited_states:
                    # next_state is not new but is not visited either
                    to_visit.append(next_state)
                else:
                    # next_state already exists and is visited
                    log.debug('State {} is already visited'.format(next_state))
                next_idx = self.automaton_states.index(next_state)
                self.automaton_transitions[curr_idx][key] = next_idx
        log.debug('to_visit = empty')
        self.automaton_built = True

    def build_parsing_table(self):
        pass

    def parse(self, string):
        log = logging.getLogger('yacv')
        if not self.is_valid:
            raise YACVError('Given grammar is not valid for chosen parsing algorithm. Parsing will not continue')
        # page 7 at below link is really helpful
        # https://www2.cs.duke.edu/courses/spring02/cps140/lects/sectlrparseS.pdf
        assert self.parsing_table_built
        assert len(string) > 0
        terminals = self.grammar.terminals
        if string[-1] != '$':
            string.append('$')
        stack = [0]
        while True:
            top = stack[-1]
            a = string[0]
            entry = self.parsing_table.at[top, (YACV_ACTION, a)]
            if entry == YACV_ERROR:
                log.error('Parse error')
                raise YACVError('YACV_ERROR entry for top = {}, a = {}'.format(top, a))
            if isinstance(entry, list):
                entry = entry[0]
            log.debug('stack top = {}, a = {}, entry = {}'.format(top, a, entry))
            if entry[0] == 's':
                stack.append(AbstractSyntaxTree(a))
                stack.append(int(entry[1:]))
                string.pop(0)
            elif entry[0] == 'r':
                prod_id =int(entry[1:])
                prod = self.grammar.prods[prod_id]
                new_tree = AbstractSyntaxTree(prod.lhs)
                new_tree.prod_id = prod_id
                popped_list = []
                if prod.rhs[0] != YACV_EPSILON:
                    for _ in range(len(prod.rhs)):
                        if not stack:
                            raise YACVError('Stack prematurely empty')
                        stack.pop(-1) # pops the state number
                        if not stack:
                            raise YACVError('Stack prematurely empty')
                        popped_list.append(stack.pop(-1)) # pops the symbol
                else:
                    new_tree.desc.append(AbstractSyntaxTree(YACV_EPSILON))
                for i in range(len(popped_list)-1, -1, -1):
                    new_tree.desc.append(popped_list[i])
                new_top = stack[-1]
                nonterminal = prod.lhs
                new_state = self.parsing_table.at[new_top, (YACV_GOTO, nonterminal)]
                stack.append(new_tree)
                if isinstance(new_state, list):
                    new_state = new_state[0]
                stack.append(int(new_state))
            elif entry == YACV_ACCEPT:
                prod = self.grammar.prods[0]
                assert prod.rhs[-1] == '$' and len(prod.rhs) == 2
                if not stack:
                    raise ValueError() # TODO: Convert this to YACVError stating an error has occurred due to stack becoming empty prematurely
                stack.pop(-1)
                if not stack:
                    raise ValueError() # TODO: Convert this to YACVError stating an error has occurred due to stack becoming empty prematurely
                tree = stack.pop(-1)
                log.info('Parse successful')
                log.debug('Final tree = {}'.format(tree))
                return tree
                break
            else:
                raise YACVError('Unknown error while parsing')
                break

    def visualize_syntaxtree(self, string, colors=None):
        global YACV_GRAPHVIZ_COLORS
        log = logging.getLogger('yacv')
        import pygraphviz as pgv
        if colors is not None:
            YACV_GRAPHVIZ_COLORS = colors 
        # Create the parse tree
        tree = self.parse(string)

        G = pgv.AGraph(name='AbstractSyntaxTree', directed=True)
        node_id = 0
        stack = [(tree, node_id)]
        terminals = self.grammar.terminals
        prods = []
        while stack:
            top, node = stack.pop(0)
            if str(node) not in G.nodes():
                G.add_node(node_id, label=top.root)
                node_id += 1
            if top.prod_id is not None:
                color = YACV_GRAPHVIZ_COLORS[top.prod_id % len(YACV_GRAPHVIZ_COLORS)]
                G.get_node(node).attr['fontcolor'] = color
            desc_ids = []
            for desc in top.desc:
                if desc.root == YACV_EPSILON:
                   label = G.get_node(node).attr['label'] 
                   label = '<' + label + ' = &#x3B5;>'
                   G.get_node(node).attr['label'] = label
                   break
                G.add_node(node_id, label=desc.root)
                G.add_edge(node, node_id, color=color)
                desc_ids.append(node_id)
                stack.append((desc, node_id))
                node_id += 1
            prods.append(desc_ids)

        # Perform a DFS to get proper order of terminals
        terminal_nodes = []
        stack = [G.nodes()[0]]
        visited = []
        while stack:
            node = stack.pop(-1)
            if node not in visited:
                visited.append(node)
                if node.attr['label'] in terminals:
                    terminal_nodes.append(node)
                log.debug(node.attr['label'])
                for i in range(len(G.successors(node))-1, -1, -1):
                    stack.append(G.successors(node)[i])
        for i, prod in enumerate(prods):
            nonterminals = []
            for node_id in prod:
                if G.get_node(node_id).attr['label'] in terminals:
                    continue
                nonterminals.append(G.get_node(node_id))
            if len(nonterminals) <= 1:
                continue
            nt = G.subgraph(nonterminals, name='Production' + str(i))
            nt.graph_attr['rank'] = 'same'
            for j in range(len(nt.nodes())-1):
                log.debug('Adding edge from c.nodes()[{}]={} to c.nodes()[{}]={}'.format(
                    j, nonterminals[j], j+1, nonterminals[j+1]
                ))
                nt.add_edge(nonterminals[j], nonterminals[j+1], \
                        style='invis', weight=YACV_GRAPHVIZ_INFINITY)

        t = G.add_subgraph(terminal_nodes, name='Terminals')
        t.graph_attr['rank'] = 'max'
        for i in range(len(t.nodes())-1):
            log.debug('Adding edge from c.nodes()[{}]={} to c.nodes()[{}]={}'.format(
                i, terminal_nodes[i], i+1, terminal_nodes[i+1]
            ))
            t.add_edge(terminal_nodes[i], terminal_nodes[i+1], style='invis')


        G.edge_attr['dir'] = 'none'
        G.node_attr['ordering'] = 'out'
        G.node_attr['shape'] = 'none'
        G.node_attr['height'] = 0
        G.node_attr['width'] = 0
        G.node_attr['margin'] = 0.1
        G.layout('dot')

        log.info('LR parse tree successfully visualized')
        return G

    def visualize_automaton(self):
        log = logging.getLogger('yacv')
        import pygraphviz as pgv
        G = pgv.AGraph(rankdir='LR', directed=True)
        G.add_node(-1, style='invis')
        for i, state in enumerate(self.automaton_states):
            label = '<U><B>State {}<BR/></B></U>'.format(i) + \
                    state.__str__(join_on='<BR/>') 
            label = label.replace(YACV_DOT, '&#xB7;')
            label = label.replace('->', '&#10132;')
            label = '<' + label + '>'
            log.debug(label)
            if len(state.reduce_items) > 0:
                # This is a reduce state
                fillcolor = '#90EE90' if state.accept else '#85CAF6'
                G.add_node(i, label=label, peripheries=2, 
                            style='filled', fillcolor=fillcolor)
                log.debug('Added reduce node')
            else:
                G.add_node(i, label=label)
                log.debug('Added node')
        G.add_edge(-1, 0)
        for state, transitions in self.automaton_transitions.items():
            for symbol, new_state in transitions.items():
                G.add_edge(state, new_state, label=symbol)

        G.node_attr['shape'] = 'box'
        G.node_attr['height'] = 0
        G.node_attr['width'] = 0
        G.node_attr['margin'] = 0.05
        G.layout('dot')
        log.info('LR automaton successfully visualized')
        return G

class LR0Parser(LRParser):
    # TODO: Can we support epsilon LR(0) parsers ?
    # Ref: Parsing Techniques - Practical Guide 2nd Edition Sec.9.5.4
    def build_automaton(self):
        if self.automaton_built:
            # TODO: Warn user
            return
        init = LRAutomatonState(self.closure(LRItem(self.grammar.prods[0], 0)))
        self.build_automaton_from_init(init)

    def build_parsing_table(self):
        log = logging.getLogger('yacv')
        if self.parsing_table_built:
            log.warn('Parsing table is already built!')
            return
        if not self.automaton_built:
            raise YACVError('LR state automaton must be built before building parsing table')
        terminals = self.grammar.terminals
        for state_id, transitions in self.automaton_transitions.items():
            state = self.automaton_states[state_id]
            if state.accept:
                col = (YACV_ACTION, '$')
                self.parsing_table.at[state_id, col] = YACV_ACCEPT
            elif len(state.reduce_items) > 0:
                for t in self.grammar.terminals:
                    col = (YACV_ACTION, t)
                    if self.parsing_table.at[state_id, col] == YACV_ERROR:
                        self.parsing_table.at[state_id, col] = []
                    for item in state.items:
                        if item.reduce:
                            prod_id = self.grammar.prods.index(item.production)
                            entry = YACV_REDUCE + str(prod_id)
                            self.parsing_table.at[state_id, col].append(entry)
                            if len(self.parsing_table.at[state_id, col]) > 1:
                                self.is_valid = False
            for symbol, new_state_id in transitions.items():
                if symbol in terminals:
                    entry = YACV_SHIFT + str(new_state_id)
                    col = (YACV_ACTION, symbol)
                else:
                    entry = str(new_state_id)
                    col = (YACV_GOTO, symbol)
                if self.parsing_table.at[state_id, col] == YACV_ERROR:
                    self.parsing_table.at[state_id, col] = []
                self.parsing_table.at[state_id, col].append(entry)
                if len(self.parsing_table.at[state_id, col]) > 1:
                    self.is_valid = False

        self.parsing_table_built = True
        if not self.is_valid:
            log.warning('Grammar is not LR(0)')
        else:
            log.info('Parsing table built successfully')

class SLR1Parser(LR0Parser):
    def build_parsing_table(self):
        log = logging.getLogger('yacv')
        if self.parsing_table_built:
            log.warn('Parsing table is already built!')
            return
        if not self.automaton_built:
            raise YACVError('LR state automaton must be built before building parsing table')
        terminals = self.grammar.terminals
        for state_id, transitions in self.automaton_transitions.items():
            state = self.automaton_states[state_id]
            if state.accept:
                col = (YACV_ACTION, '$')
                self.parsing_table.at[state_id, col] = YACV_ACCEPT
            elif len(state.reduce_items) > 0:
                for item in state.items:
                    if item.reduce:
                        lhs = item.production.lhs
                        follow = self.grammar.nonterminals[lhs]['follow']
                        prod_id = self.grammar.prods.index(item.production)
                        entry = YACV_REDUCE + str(prod_id)
                        for symbol in follow:
                            col = (YACV_ACTION, symbol)
                            if self.parsing_table.at[state_id, col] == YACV_ERROR:
                                self.parsing_table.at[state_id, col] = []
                            self.parsing_table.at[state_id, col].append(entry)
                            if len(self.parsing_table.at[state_id, col]) > 1:
                                self.is_valid = False
            for symbol, new_state_id in transitions.items():
                if symbol in terminals:
                    entry = YACV_SHIFT + str(new_state_id)
                    col = (YACV_ACTION, symbol)
                else:
                    entry = str(new_state_id)
                    col = (YACV_GOTO, symbol)
                if self.parsing_table.at[state_id, col] == YACV_ERROR:
                    self.parsing_table.at[state_id, col] = []
                self.parsing_table.at[state_id, col].append(entry)
                if len(self.parsing_table.at[state_id, col]) > 1:
                    self.is_valid = False

        self.parsing_table_built = True
        if not self.is_valid:
            log.warning('Grammar is not SLR(1)')
        else:
            log.info('Parsing table built successfully')

class LR1Parser(LRParser): 
    def build_automaton(self):
        if self.automaton_built:
            # TODO: Warn user
            return
        init = LRAutomatonState(self.closure(LRItem(
            self.grammar.prods[0], 0, ['$'])))
        self.build_automaton_from_init(init)
        self.automaton_built = True

    def build_parsing_table(self):
        log = logging.getLogger('yacv')
        if self.parsing_table_built:
            log.warn('Parsing table is already built!')
            return 
        if not self.automaton_built:
            raise YACVError('LR state automaton must be built before building parsing table')
        terminals = self.grammar.terminals
        for state_id, transitions in self.automaton_transitions.items():
            state = self.automaton_states[state_id]
            if len(state.reduce_items) > 0:
                # This is kinda dumb, why am I not using reduce_items directly ?
                # TODO: Fix this
                for item in state.items:
                    if item.reduce:
                        prod = item.production
                        prod_id = self.grammar.prods.index(prod)
                        if prod_id == 0:
                            col = (YACV_ACTION, '$')
                            self.parsing_table.at[state_id, col] = YACV_ACCEPT
                            continue
                        lookaheads = item.lookaheads
                        entry = 'r' + str(prod_id)
                        for symbol in item.lookaheads:
                            col = (YACV_ACTION, symbol)
                            if self.parsing_table.at[state_id, col] == YACV_ERROR:
                                self.parsing_table.at[state_id, col] = []
                            self.parsing_table.at[state_id, col].append(entry)
                            if len(self.parsing_table.at[state_id, col]) > 1:
                                self.is_valid = False
            for symbol, new_state_id in transitions.items():
                if symbol in terminals:
                    entry = 's' + str(new_state_id)
                    col = (YACV_ACTION, symbol)
                else:
                    entry = str(new_state_id)
                    col = (YACV_GOTO, symbol)
                if self.parsing_table.at[state_id, col] == YACV_ERROR:
                    self.parsing_table.at[state_id, col] = []
                self.parsing_table.at[state_id, col].append(entry)
                if len(self.parsing_table.at[state_id, col]) > 1:
                    self.is_valid = False
        self.parsing_table_built = True
        if not self.is_valid:
            log.warning('Grammar is not valid')
        else:
            log.info('Parsing table built successfully')

class LALR1Parser(LR1Parser): 
    def build_automaton(self):
        log = logging.getLogger('yacv')
        if self.automaton_built:
            log.warn('Automaton is already built!')
            return
        init = LRAutomatonState(self.closure(LRItem(
            self.grammar.prods[0], 0, ['$'])))
        self.build_automaton_from_init(init)

        def get_core(state):
            core = ''
            for item in state.items:
                core += str(LRItem(item.production, item.dot_pos)) + '\n'
            return core 

        state_core_dict = OrderedDict()
        state_id = 0
        for i, state in enumerate(self.automaton_states):
            core = get_core(state)
            if core not in state_core_dict.keys():
                state_core_dict[core] = {
                    "state_id" : state_id,
                    "state_list" : []
                }
                state_id += 1
            state_core_dict[core]['state_list'].append(i)
        new_states = []
        for key, info in state_core_dict.items():
            states = info['state_list']
            if len(states) == 1:
                new_states.append(self.automaton_states[states[0]])
                new_states[-1].update_shift_reduce_items()
                new_states[-1].update_conflicts()
                continue 
            new_state = self.automaton_states[states[0]]
            for i, state_id in enumerate(states[1:]):
                state = self.automaton_states[state_id]
                for j, item in enumerate(state.items):
                    assert new_state.items[j].production == item.production
                    assert new_state.items[j].dot_pos == item.dot_pos 
                    lookaheads = set(new_state.items[j].lookaheads)
                    lookaheads = lookaheads.union(set(item.lookaheads))
                    new_state.items[j].lookaheads = sorted(list(lookaheads))
            new_states.append(new_state)
            new_states[-1].update_shift_reduce_items()
            new_states[-1].update_conflicts()

        new_automaton_transitions = OrderedDict()
        for state_id, info in self.automaton_transitions.items():
            core = get_core(self.automaton_states[state_id])
            curr_state_id = state_core_dict[core]['state_id']
            if curr_state_id not in new_automaton_transitions.keys():
                new_automaton_transitions[curr_state_id] = OrderedDict()
            for symbol, new_state_id in info.items():
                core = get_core(self.automaton_states[new_state_id])
                next_state_id = state_core_dict[core]['state_id']
                new_automaton_transitions[curr_state_id][symbol] = \
                        next_state_id 
        self.automaton_states = new_states 
        self.automaton_transitions = new_automaton_transitions
        self.automaton_built = True

if __name__ == '__main__':
    import sys
    from utils import setup_logger
    setup_logger()
    if len(sys.argv) > 2:
        #lr0 = LR0Parser(sys.argv[1])
        p = LALR1Parser(sys.argv[1])
        string = sys.argv[2]
    else:
        #lr0 = LR0Parser()
        p = LALR1Parser()
        string = sys.argv[1]
    p.visualize_automaton()
    string = 'id + id * ( id / id / id * id ) - id'
    string = [x.strip() for x in string.split(' ')]
    p.visualize_syntaxtree(string)
    
