import logging 
from collections import OrderedDict
from pprint import pprint
from yacv.constants import *
class Production(object):
    def __init__(self, lhs=None, rhs=[]):
        self.lhs = lhs
        self.rhs = rhs

    def __str__(self):
        rhs = 'ϵ' if self.rhs[0] == YACV_EPSILON else ''.join(self.rhs)
        return '{} -> {}'.format(self.lhs, rhs)
    
    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        if not isinstance(other, Production):
            return False
        return self.lhs == other.lhs and self.rhs == other.rhs
    
    def __ne__(self, other):
        return not self == other
def first(g, s):
    # g: Grammar object
    # s: RHS or Part of RHS as list
    if not s:
        return set() # empty set
    if s[0] == YACV_EPSILON:
        return set([YACV_EPSILON]) # set with epsilon in it
    if s[0] not in g.nonterminals.keys():
        return set([s[0]])
    # At this point, s[0] must be a non terminal
    ret = set()
    for prodno in g.nonterminals[s[0]]['prods_lhs']:
        rhs = g.prods[prodno].rhs
        if rhs[0] == s[0]:
            # left recursion
            continue
        x = first(g, rhs)
        ret = ret.union(x)

    if YACV_EPSILON in ret:
        x = first(g, s[1:])
        ret = ret.union(x)
    return ret

class Grammar(object):
    def __init__(self, fname='simple-grammar.txt'):
        lines = [x.strip() for x in open(fname).readlines()] 
        self.prods = [] # list containing all the productions
        all_symbols = set()
        for line in lines:
            # TODO: If ValueError is generated when splitting
            # report unrecognized grammar
            if line == '':
                continue
            lhs, rhs = line.split('->')
            lhs = lhs.strip()
            rhs = [x for x in rhs.split(' ') if x]
            # TODO: find a better way to do this
            for i, _ in enumerate(rhs):
                if rhs[i] == "\'\'":
                    rhs[i] = YACV_EPSILON
            self.prods.append(
                Production(lhs, rhs)
            )
            all_symbols = all_symbols.union(rhs)
        # Augment the grammar
        self.prods.insert(0, Production('S\'', [self.prods[0].lhs, '$']))
        # Accumulate nonterminal information
        self.nonterminals = OrderedDict()
        for i, prod in enumerate(self.prods):
            lhs, rhs = prod.lhs, prod.rhs
            if lhs not in self.nonterminals.keys():
                self.nonterminals[lhs] = {
                    # number of productions this nonterminal is on the LHS of
                    'prods_lhs' : [i],
                    # where does this non terminal appear on RHS ? 
                    # what prod and what place ?
                    'prods_rhs' : [],
                    'first'     : set(),
                    'follow'    : set(),
                    'nullable'  : False
                }
            else:
                self.nonterminals[lhs]['prods_lhs'].append(i)
        self.terminals = all_symbols.difference(set(self.nonterminals.keys()))
        if YACV_EPSILON in self.terminals:
            self.terminals = self.terminals.difference(set([YACV_EPSILON]))
        self.terminals.add('$')
        self.terminals = sorted(self.terminals)
        # Update nonterminals_on_rhs for every prod using above data
        for prodno, prod in enumerate(self.prods):
            lhs, rhs = prod.lhs, prod.rhs
            for i, symbol in enumerate(rhs):
                if symbol in self.nonterminals.keys():
                    self.nonterminals[symbol]['prods_rhs'].append((prodno, i))
        self.build_first()
        self.build_follow()

    def build_first(self):
        # inefficient method, but should work fine for most small grammars
        for nt in self.nonterminals.keys():
            tmp = first(self, [nt])
            self.nonterminals[nt]['first'] = tmp
            for prod_id in self.nonterminals[nt]['prods_lhs']:
                if self.prods[prod_id].rhs[0] == YACV_EPSILON:
                    self.nonterminals[nt]['nullable'] = True 
        
        changed = True
        while changed:
            changed = False 
            for nt in self.nonterminals.keys():
                for prod_id in self.nonterminals[nt]['prods_lhs']:
                    rhs = self.prods[prod_id].rhs
                    count = 0
                    for symbol in rhs:
                        if symbol in self.nonterminals.keys() and \
                        self.nonterminals[symbol]['nullable']:
                            count += 1
                    if count == len(rhs) and not self.nonterminals[nt]['nullable']:
                        self.nonterminals[nt]['nullable'] = True
                        changed = True

        for nt in self.nonterminals.keys():
            f = self.nonterminals[nt]['first']
            if self.nonterminals[nt]['nullable']:
                self.nonterminals[nt]['first'] = f.union(set([YACV_EPSILON]))
            else:
                self.nonterminals[nt]['first'] = f.difference(set([YACV_EPSILON]))

    def build_follow(self):
        log = logging.getLogger('yacv')
        self.nonterminals[self.prods[0].lhs]['follow'].add('$')
        for nt in self.nonterminals.keys():
            # Where does this symbol occur on RHS ?
            s = set()
            for prodno, idx in self.nonterminals[nt]['prods_rhs']:
                log.debug('Needed FIRST({}) = {} for FOLLOW({})'.format(
                    self.prods[prodno].rhs[idx+1:], 
                    first(self, self.prods[prodno].rhs[idx+1:]), 
                    nt
                ))
                f = first(self, self.prods[prodno].rhs[idx+1:])
                if not f or YACV_EPSILON in f:
                    f.add('$')
                s = s.union(f)
                s = s.difference(set([YACV_EPSILON]))
            self.nonterminals[nt]['follow'] = s
            log.debug('FOLLOW({}) = {}'.format(nt, s))
        for prod in self.prods:
            log.debug('At production {}'.format(prod))
            # Is there a production A -> BC such that C is NULLABLE ?
            lhs, rhs = prod.lhs, prod.rhs
            reversed_rhs = rhs[::-1]
            for i, symbol in enumerate(reversed_rhs):
                log.debug('i = {}, symbol = {}'.format(i, symbol))
                if symbol not in self.nonterminals.keys():
                    break
                if self.nonterminals[symbol]['nullable'] and (i+1) < len(rhs):
                    if reversed_rhs[i+1] in self.terminals:
                        continue
                    s1 = self.nonterminals[reversed_rhs[i+1]]['follow']
                    s2 = self.nonterminals[lhs]['follow']
                    s1 = s1.union(s2)
                    self.nonterminals[reversed_rhs[i+1]]['follow'] = s1
                    if i == 0:
                        s3 = self.nonterminals[symbol]['follow']
                        s3 = s3.union(s2)
                        self.nonterminals[symbol]['follow'] = s3
                        log.debug('Production {} has nullable symbol {} at the end, updated FOLLOW({}) = {}'.format(prod, symbol, symbol, s3))
                    log.debug('Production {} has nullable symbol {}, changed FOLLOW({}) to {}'.format(prod, symbol, reversed_rhs[i+1], s1))
            if rhs[-1] in self.nonterminals.keys():
                self.nonterminals[rhs[-1]]['follow'] = \
                        self.nonterminals[rhs[-1]]['follow'].union(
                            self.nonterminals[lhs]['follow']
                        )
            log.debug('End of iteration' + 16*'-')

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 1:
        g = Grammar()
    else:
        g = Grammar(sys.argv[1])
    pprint(g.prods)
    print(64*'-')
    for nt in g.nonterminals.keys():
        print('FIRST({}) = {}'.format(nt, g.nonterminals[nt]['first']))
    print(64*'-')
    for nt in g.nonterminals.keys():
        print('FOLLOW({}) = {}'.format(nt, g.nonterminals[nt]['follow']))
