# only for being able to run via `manimgl`
import sys
sys.path.append('/home/ashutosh/parser-vis/')
try:
    from manimlib import *
    manimce = False 
except ImportError as e:
    from manim import *
    manimce = True 
import argparse
import logging 
import pygraphviz as pgv
import numpy as np
from copy import deepcopy
from yacv.utils import *
from yacv.constants import *
from yacv.ll1 import *
from yacv.lr import *
from yacv.mobjects import *

class LL1ParsingVisualizer(Scene):
    def setup(self, parser=None, string=None, colors=None, **kwargs):
        if hasattr(self, 'grammar_setup_done') and self.grammar_setup_done:
            super().setup(**kwargs)
            return
        self.parser = parser 
        if not parser.is_ll1:
            raise YACVError('Grammar is not valid for chosen parsing algorithm. Parsing will not continue')
        if isinstance(string, str):
            string = string.split(' ')
            string = [x for x in string if x]
        if string[-1] != '$':
            string.append('$')
        self.string = string 
        self.colors = colors 
        self.grammar_setup_done = True
        super().setup(**kwargs)

    def construct(self):
        log = logging.getLogger('yacv')
        p = self.parser
        assert p is not None
        string = self.string 
        tree = AbstractSyntaxTree('S\'')
        curr_node_id = 0 # Assigning the node ids as we build the tree 
        tree.node_id = curr_node_id 
        curr_node_id += 1
        stack = [tree]
        popped_stack = []

        old_stack_mobject = StackMobject(stack)
        prev_mobject = None 
        curr_mobject = None 
        status_mobject  = Text('START')
        status_mobject.scale(YACV_MANIM_STATUS_SCALE)
        status_pos = 5.5*LEFT + 3*UP
        string_text = [YACV_MANIM_STRING_LEADER]
        string_text.extend([prepare_text(x) for x in string])
        string_text.append(']')
        string_mobject = Tex(*string_text)
        string_mobject.arrange(RIGHT, buff=0.25)
        string_pos = 0*LEFT + 3.5*DOWN
        string_mobject.move_to(string_pos)
        string_mobject[1].set_color(RED)
        string_mobject.scale(YACV_MANIM_STRING_SCALE)
        status_mobject.move_to(status_pos)

        self.add(status_mobject)
        self.add(string_mobject)
        self.add(old_stack_mobject)
        # Assigning the stack top to a variable loses the tree ref 
        # https://stackoverflow.com/questions/986006/how-do-i-pass-a-variable-by-reference
        while stack[-1].root != '$' and stack[-1].root != '\\$':
            a = string[0]
            if a == '\\$':
                a = '$'
            if stack[-1].root == a:
                popped_stack.append(stack.pop(-1))
                a = string.pop(0)
                new_status_mobject = Text('Match {}'.format(a))
                new_status_mobject.scale(YACV_MANIM_STRING_SCALE)
                new_status_mobject.move_to(status_pos)
                self.play(Transform(status_mobject, new_status_mobject))
                self.play(ShowCreationThenDestructionAround(new_status_mobject))
                self.remove(new_status_mobject)
            elif stack[-1].root in p.grammar.terminals:
                raise ValueError('Error because top = {}, terminal'.format(stack[-1].root))
            elif p.parsing_table.at[stack[-1].root.replace('\\$', '$'), a] ==\
                    YACV_ERROR:
                raise ValueError('Error entry in the parsing table for top = {}, a = {}'.format(stack[-1].root, a))
            elif p.parsing_table.at[stack[-1].root.replace('\\$', '$'), a] !=\
                    YACV_ACCEPT:
                prod = p.parsing_table.at[stack[-1].root, a][0]
                log.info(prod)
                prod_text = '{} '.format(prod.lhs)
                prod_text += '$\\rightarrow$' if manimce else '\\rightarrow'
                if prod.rhs[0] == YACV_EPSILON:
                    prod_text += ' $\\epsilon$' if manimce else ' \\epsilon'
                else:
                    prod_text += ' {}'.format(''.join(prod.rhs)\
                            .replace('$', '\\$'))
                new_status_mobject = Tex(prod_text)
                new_status_mobject.scale(YACV_MANIM_STATUS_SCALE)
                new_status_mobject.move_to(status_pos)
                self.play(Transform(status_mobject, new_status_mobject))
                self.play(ShowCreationThenDestructionAround(new_status_mobject))
                self.remove(new_status_mobject)
                stack[-1].prod_id = p.grammar.prods.index(prod)
                desc_list = []
                for symbol in prod.rhs:
                    symbol = symbol.replace('$', '\\$')
                    x = AbstractSyntaxTree(symbol)
                    x.node_id = curr_node_id 
                    curr_node_id += 1
                    stack[-1].desc.append(x)
                    desc_list.append(x)
                popped_stack.append(stack.pop(-1))
                if prod.rhs[0] != YACV_EPSILON:
                    for i in range(len(desc_list)-1,-1,-1):
                        stack.append(desc_list[i])
            # Starting Animations
            all_anims = []
            string_text = [YACV_MANIM_STRING_LEADER]
            string_text.extend([prepare_text(x) for x in string])
            string_text.append(']')
            log.debug(string_text)
            new_string_mobject = Tex(*string_text)
            new_string_mobject.arrange(RIGHT, buff=0.25)
            new_string_mobject[1].set_color(RED)
            new_string_mobject.move_to(string_pos)
            new_string_mobject.scale(YACV_MANIM_STRING_SCALE)
            curr_stack_mobject = StackMobject(stack)
            anim_s = transform_stacks(old_stack_mobject, curr_stack_mobject)
            curr_mobject = GraphvizMobject(stack_to_graphviz([popped_stack[0]]\
                    , p.grammar, self.colors))
            if prev_mobject is not None:
                anim_t = transform_graphviz_graphs(prev_mobject, curr_mobject)
            else:
                anim_t = [ShowCreation(curr_mobject)]
            all_anims.extend(anim_t)
            all_anims.extend(anim_s)
            all_anims.append(Transform(string_mobject, new_string_mobject))
            self.play(*all_anims)
            self.wait(1)
            self.remove(old_stack_mobject)
            self.remove(new_string_mobject)
            if prev_mobject is not None:
                self.remove(prev_mobject)
            old_stack_mobject = curr_stack_mobject
            prev_mobject = curr_mobject 
            # Ending Animations 
            log.debug(popped_stack)
        new_status_mobject = Tex('ACCEPT')
        new_status_mobject.scale(YACV_MANIM_STATUS_SCALE)
        new_status_mobject.move_to(status_pos)
        new_status_mobject.set_color(YELLOW)
        self.play(Transform(status_mobject, new_status_mobject))
        self.play(ShowCreationThenDestructionAround(new_status_mobject))
        self.wait(1)
        self.remove(new_status_mobject)
        return 


class LRParsingVisualizer(Scene):
    def setup(self, parser=None, string=None, colors=None, **kwargs):
        if hasattr(self, 'grammar_setup_done') and self.grammar_setup_done:
            super().setup(**kwargs)
            return
        self.parser = parser
        if not parser.is_valid:
            raise YACVError('Grammar is not valid for chosen parsing algorithm. Parsing is not continue')
        if isinstance(string, str):
            string = string.split(' ')
            string = [x for x in string if x]
        if string[-1] != '$':
            string.append('$')
        self.string = string
        self.colors = colors
        self.grammar_setup_done = True
        super().setup(**kwargs)

    def construct(self):
        p = self.parser 
        assert p is not None 
        string = self.string 
        log = logging.getLogger('yacv')
        stack = [0]
        old_stack_mobject = None
        prev_mobject = None 
        curr_mobject = None 
        curr_node_id = 0 # Assigning the node ids as we build the tree 
        status_mobject  = Text('START')
        status_mobject.scale(YACV_MANIM_STATUS_SCALE)
        status_pos = 5.5*LEFT + 3*UP
        string_text = [YACV_MANIM_STRING_LEADER]
        string_text.extend([prepare_text(x) for x in string])
        string_text.append(']')
        log.debug(string_text)
        string_mobject = Tex(*string_text)
        string_mobject.arrange(RIGHT, buff=0.25)
        string_pos = 0*LEFT + 3.5*DOWN
        string_mobject.move_to(string_pos)
        string_mobject[1].set_color(RED)
        string_mobject.scale(YACV_MANIM_STRING_SCALE)
        status_mobject.move_to(status_pos)
        self.add(status_mobject)
        self.add(string_mobject)
        while True:
            top = stack[-1]
            a = string[0]
            entry = p.parsing_table.at[top, (YACV_ACTION, a)]
            if old_stack_mobject is None:
                old_stack_mobject = StackMobject(stack)
                self.add(old_stack_mobject)
            if entry == YACV_ERROR:
                # TODO: Get better error messages here
                raise ValueError('Parsing error. Got YACV_ERROR entry for top = {}, a = {}'.format(top, a))
            if isinstance(entry, list):
                # TODO: Can we implement some precedence here ?
                # Like, if it's shift reduce conflict, user configures the 
                # default action ?
                # Shouldn't be difficult, I already have a provision for 
                # preferred action in `LRAutomatonState`
                entry = entry[0]
            # Actual parsing logic starts 
            if entry[0] == 's':
                t = AbstractSyntaxTree(a)
                t.node_id = curr_node_id 
                curr_node_id += 1
                stack.append(t)
                stack.append(int(entry[1:]))
                string.pop(0)
                # Starting Animation 
                new_status_mobject=Text('SHIFT {}'.format(int(entry[1:])))
                new_status_mobject.move_to(status_pos)
                new_status_mobject.scale(YACV_MANIM_STATUS_SCALE)
                self.play(Transform(status_mobject, new_status_mobject))
                self.play(ShowCreationThenDestructionAround(new_status_mobject))
                self.wait(1)
                self.remove(new_status_mobject)
                all_anims = []
                curr_stack_mobject = StackMobject(stack)
                anim_s = transform_stacks(old_stack_mobject,curr_stack_mobject)
                curr_mobject = GraphvizMobject(stack_to_graphviz(stack, \
                            p.grammar, self.colors))
                string_text = [YACV_MANIM_STRING_LEADER]
                string_text.extend([prepare_text(x) for x in string])
                string_text.append(']')
                new_string_mobject = Tex(*string_text)
                new_string_mobject.arrange(RIGHT, buff=0.25)
                new_string_mobject[1].set_color(RED)
                new_string_mobject.move_to(string_pos)
                new_string_mobject.scale(YACV_MANIM_STRING_SCALE)
                if prev_mobject is not None:
                    anim_t = transform_graphviz_graphs(prev_mobject, \
                            curr_mobject)
                else:
                    anim_t = [ShowCreation(curr_mobject)]
                all_anims.extend(anim_s)
                all_anims.extend(anim_t)
                all_anims.append(Transform(string_mobject, new_string_mobject))
                self.play(*all_anims)
                self.wait(1)
                self.remove(old_stack_mobject)
                self.remove(new_string_mobject)
                if prev_mobject is not None:
                    self.remove(prev_mobject)
                old_stack_mobject = curr_stack_mobject
                prev_mobject = curr_mobject 
                # Ending Animation 
            elif entry[0] == 'r':
                prod_id = int(entry[1:])
                prod = p.grammar.prods[prod_id]
                log.info(prod)
                new_tree = AbstractSyntaxTree(prod.lhs)
                new_tree.prod_id = prod_id 
                new_tree.node_id = curr_node_id 
                curr_node_id += 1
                
                # Starting animation 
                # highlight 2 * len(prod.rhs) elements on the stack 
                l = old_stack_mobject.stack_len
                to_highlight = 2*len(prod.rhs) if l > 2*len(prod.rhs) else l 
                keys = list(old_stack_mobject.elements.keys())
                anims = []
                for i in keys[-to_highlight:]:
                    anims.append(Indicate(old_stack_mobject.elements[i]))
                self.play(*anims)
                self.wait(1) 
                
                if manimce:
                    prod_text = '{} $\\rightarrow$'.format(prod.lhs)
                else:
                    prod_text = '{} \\rightarrow'.format(prod.lhs)
                if prod.rhs[0] == YACV_EPSILON:
                    prod_text += ' $\\epsilon$' if manimce else ' \\epsilon'
                else:
                    prod_text += ' {}'.format(' '.join(prod.rhs))
                new_status_mobject = Tex(prod_text)
                new_status_mobject.move_to(status_pos)
                new_status_mobject.scale(YACV_MANIM_STATUS_SCALE)
                self.play(Transform(status_mobject, new_status_mobject))
                self.play(ShowCreationThenDestructionAround(new_status_mobject))
                self.wait(1)
                self.remove(new_status_mobject)
                # Ending animation

                # I'm getting the popped list and then traversing it in 
                # reverse direction again just so that memory references 
                # are proper
                # TODO: can this be optimized ?
                popped_list = []
                if prod.rhs[0] != YACV_EPSILON:
                    for _ in range(len(prod.rhs)):
                        if not stack:
                            raise ValueError('Parsing Error: Stack prematurely empty')
                        stack.pop(-1)
                        if not stack:
                            raise ValueError('Parsing Error: Stack prematurely empty')
                        popped_list.append(stack.pop(-1))
                else:
                    # Note here that we don't need to increment `curr_node_id`
                    # This is because `epsilon` nodes are merged with their 
                    # parents when converting AST to Graphviz
                    new_tree.desc.append(AbstractSyntaxTree(YACV_EPSILON))
                for i in range(len(popped_list)-1,-1,-1):
                    new_tree.desc.append(popped_list[i])
                # Starting Animation 
                curr_stack_mobject = StackMobject(stack)
                anims = transform_stacks(old_stack_mobject, curr_stack_mobject)
                self.play(*anims)
                self.wait(1)
                old_stack_mobject = curr_stack_mobject
                # Ending Animation 
                new_top = stack[-1]
                nonterminal = prod.lhs 
                new_state = p.parsing_table.at[new_top, (YACV_GOTO, nonterminal)]
                stack.append(new_tree)
                if isinstance(new_state, list):
                    new_state = new_state[0]
                stack.append(int(new_state))
                # Starting Animation 
                all_anims = []
                curr_stack_mobject = StackMobject(stack)
                anim_s = transform_stacks(old_stack_mobject,curr_stack_mobject)
                curr_mobject = GraphvizMobject(stack_to_graphviz(stack, \
                        p.grammar, self.colors))
                if prev_mobject == None:
                    anim_t = [ShowCreation(curr_mobject)]
                else:
                    anim_t = transform_graphviz_graphs(prev_mobject, curr_mobject)
                all_anims.extend(anim_s)
                all_anims.extend(anim_t)
                self.play(*all_anims)
                self.wait(1)
                self.remove(old_stack_mobject)
                self.remove(prev_mobject)
                old_stack_mobject = curr_stack_mobject
                prev_mobject = curr_mobject 
                # Ending Animation 
            elif entry == YACV_ACCEPT:
                prod = p.grammar.prods[0]
                assert prod.rhs[-1] == '$' and len(prod.rhs) == 2
                # Parsing successful 
                # TODO: Log that parsing is successful 
                new_status_mobject = Tex("ACCEPT")
                new_status_mobject.move_to(status_pos)
                new_status_mobject.set_color(YELLOW)
                new_status_mobject.scale(YACV_MANIM_STATUS_SCALE)
                self.play(Transform(status_mobject, new_status_mobject))
                self.play(ShowCreationThenDestructionAround(new_status_mobject))
                self.remove(new_status_mobject)
                curr_mobject = GraphvizMobject(stack_to_graphviz(stack, \
                        p.grammar, self.colors))
                anims = transform_graphviz_graphs(prev_mobject, curr_mobject)
                new_string_mobject = Tex(YACV_MANIM_STRING_LEADER, ']')
                new_string_mobject.move_to(string_pos)
                new_string_mobject.scale(YACV_MANIM_STRING_SCALE)
                anims.append(Transform(string_mobject, new_string_mobject))
                anims.append(FadeOut(string_mobject))
                self.play(*anims)
                break 
            else:
                raise ValueError('Unknown error while parsing')
        return 


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', action='store_true')
    parser.add_argument('-l', action='store_true')
    parser.add_argument('-o', action='store_true')
    setup_logger()
    """
    bme = BasicManimExample()
    bme.setup()
    bme.construct()
    """
    if manimce:
        from manim import config 
        pprint(manimce_config)
        for k, v in manimce_config.items():
            print('Set {} = {}'.format(k, v))
            config[k] = v
        vis = LRParsingVisualizer()
    else:
        vis = LRParsingVisualizer(**manim_config)
    vis.setup('expression-grammar.txt', 'id')
    # vis.setup('expression-grammar.txt', 'id + id')
    if manimce:
        vis.render()
    else:
        vis.run()
    """
    vis = LL1ParsingVisualizer(**manim_config)
    vis.setup('ll1-expression-grammar.txt', 'id')
    vis.run()
    """
