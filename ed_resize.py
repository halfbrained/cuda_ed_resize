import os
from cudatext import *

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')

option_minimize_xy = 'y' # x,y,xy
option_min_focus = 1 # 0=stay, 1=go to last used

''' file:///install.inf
'''

SPLITTERS = [
    SPLITTER_G1,
    SPLITTER_G2,
    SPLITTER_G3,
    SPLITTER_G4,
    SPLITTER_G5,
]

class Command:

    def __init__(self):
        global option_minimize_xy
        global option_min_focus

        option_minimize_xy = ini_read(fn_config, 'editors_resizer', 'minimize_preference', option_minimize_xy)
        option_min_focus = int(ini_read(fn_config, 'editors_resizer', 'min_focus', str(option_min_focus)))

        self.group_ratios = {} # (rx,ry,grouping)

        self._last_config = None
        # try loading saved state
        state = ini_read(fn_config, 'editors_resizer', '_state', 'non')
        if state != 'non':
            ini_write(fn_config, 'editors_resizer', '_state', 'non')

            last_grouping, active_group, ratios = state.split(';')
            ratios = ratios.split('|')
            self._last_config = (int(last_grouping), int(active_group), [float(r) for r in ratios])

    def config(self):
        ini_write(fn_config, 'editors_resizer', 'minimize_preference',  option_minimize_xy)
        ini_write(fn_config, 'editors_resizer', 'min_focus',            str(option_min_focus))
        file_open(fn_config)

    def on_focus(self, ed_self):
        group = ed.get_prop(PROP_INDEX_GROUP)
        self.unmin_group(group)

    def on_exit(self, ed_self):
        # keep minimized/maximized state after restart
        if self._last_config:
            last_grouping, active_group, splitters = self._last_config
            ratios = '|'.join(['{:.3}'.format(r) for r in splitters])
            s = '{};{};{}'.format(last_grouping, active_group, ratios)
            ini_write(fn_config, 'editors_resizer', '_state', s)

    def tgl_max(self):
        grouping = app_proc(PROC_GET_GROUPING, '')

        #pass; print(f'MAX: Grouping:{grouping}')

        if grouping == GROUPS_ONE:
            return

        l = Layout()
        self.l = l

        if self.try_revert_max(grouping):
            return

        x,y = l.curpos

        spl_poss = []
        splsx,splsy = l.enum_spls('x', x, y), l.enum_spls('y', x, y)
        for i,j,spl_id in [*splsx, *splsy]:
            if i < x  or  j < y:
                spl_poss.append((spl_id, 0))
            else:
                spl = l.spl_info(spl_id)
                if spl_id in LAYOUT_SPLITTERS[grouping]:
                    spl_poss.append((spl_id, spl.size))

        #pass; print(f' + MAX:spl poss: {spl_poss}')

        # save for try_revert_max
        self._last_config = (grouping, l.gind, self._get_splitters_ratios())

        self.set_splitters_pos(grouping, *spl_poss)

    def tgl_min(self):
        grouping = app_proc(PROC_GET_GROUPING, '')
        if grouping == GROUPS_ONE:
            return

        edi = ed.get_prop(PROP_INDEX_GROUP)
        if self.unmin_group(edi):
            return

        #pass; print(f'MIN: Grouping:{grouping}')

        l = Layout()
        self.l = l
        x,y = l.curpos

        resizes = self._prepare_resizes()

        # check if corner on T-intersec
        if len(resizes) == 2:
            r0,r1 = resizes
            dirx = 1 if -r0[1] > 0 else -1
            diry = 1 if -r1[1] > 0 else -1
            splx,sply = self._get_layout_splitters(x, y, dirx, diry)
            
            if r0[0] != r1[0]  and  (splx != 0 and sply != 0):

                if type(l.layout[splx][sply+diry]) == str: # found editor - T intersec
                    resizes = [r0] # x resize

                elif type(l.layout[splx+dirx][sply]) == str:
                    resizes = [r1] # y resize

        if len(resizes) == 2:
            r0,r1 = resizes
            if r0[0] != r1[0]: # x,y - corner
                resizes = [r for r in resizes if r[0] in option_minimize_xy]

            else:
                resizes = [resizes[0]]
                
        self.save_group_ratios(x, y, edi, grouping)

        for r in resizes:
            ax = r[0]
            items = self._get_min_ax_layout(ax, minimized_group=edi)
            self.set_splitters_pos(grouping, *items)

        if option_min_focus == 1:
            self.focus_last_ed(skip_group=self.l.gind)
            

    def unmin_group(self, group):
        grouping = app_proc(PROC_GET_GROUPING, '')
        if grouping == GROUPS_ONE:
            return

        l = Layout()
        self.l = l
        x,y = l.curpos

        edt = ed_group(group)
        rx,ry,saved_grouping = self.group_ratios.get(group, (None, None, None))

        if saved_grouping != grouping:
            rx,ry = 1,1

        (w,spl_w),(h,spl_h) = l.get_ed_size('x'), l.get_ed_size('y')

        def unmin_ax(ax, ratio, ed_size): #SKIP
            if ed_size < 0:
                return False

            size = l.size(ax)


            if ed_size < 30  and  size != -1: # expand horizontally
                ratio = ratio or 1

                ax_grs = l.enum_groups(ax=ax, ax_x=x, ax_y=y)
                group_sizes = [l.get_ed_size(ax, (x,y))[0] for x,y,gr_s in ax_grs]

                group_opened_sizes = [w for w in group_sizes  if w > 30]

                # not sure why +1 works...
                new_average_width = (sum(group_opened_sizes) + ed_size) / (len(group_opened_sizes) + 1)
                new_gr_size = round(ratio*new_average_width)

                spl_poss = []
                prev_old, prev_new, spl_w = 0, 0, 0
                for gr_s,spl_id,pos in l.enum_pairs(ax, x, y):
                    if gr_s == l.edis:
                        newpos = round(prev_new + spl_w + new_gr_size)
                    else:
                        prev_ratio = (pos - prev_old - spl_w)/(sum(group_opened_sizes))
                        space_left = (sum(group_opened_sizes)+10 - new_gr_size)
                        newpos = round(prev_new + spl_w + space_left*prev_ratio) - 1


                    spl_poss.append((spl_id, newpos))
                    prev_old, prev_new = pos, newpos 
                    spl_w = 4

                self.set_splitters_pos(grouping, *spl_poss)
                return True

            return False

        done_x = unmin_ax('x', ratio=rx, ed_size=w)
        done_y = unmin_ax('y', ratio=ry, ed_size=h)
        return done_x or done_y

    def reset_sizes(self):
        grouping = app_proc(PROC_GET_GROUPING, '')
        if grouping == GROUPS_ONE:
            return

        l = Layout()
        self.l = l

        spls_vis = {spl_id:(x,y,spl_id)  for x,y,spl_id in l.enum_spls()  if l.spl_info(spl_id).isvis}

        resizes = []
        for x,y,spl_id in spls_vis.values():
            spl = l.spl_info(spl_id)
            lcount = l.lw  if spl.isvert else  l.lh
            lpos = x  if spl.isvert else  y
            edsize = spl.size/((lcount+1)/2)
            newpos = edsize * ((lpos+1)/2)
            resizes.append((spl_id, int(newpos)))

        self.set_splitters_pos(grouping, *resizes)

    def try_revert_max(self, grouping):
        if self._last_config is not None:
            last_grouping, active_group, splitters = self._last_config
            self._last_config = None

            # check that other groups are minimized
            grs = {gr_s:(x,y,gr_s)  for x,y,gr_s in self.l.enum_groups()  if gr_s != self.l.edis} # except active
            for x,y,gr_s in grs.values():
                sizex,sizey = self.l.get_ed_size('x', (x,y))[0], self.l.get_ed_size('y', (x,y))[0]
                if (sizex == -1 or sizex > 30)  and  (sizey == -1 or sizey > 30):
                    return

            if grouping == last_grouping:
                self.load_splitters_ratios(grouping, splitters)
                return True

    def save_group_ratios(self, x, y, edi, grouping):
        rx = self._get_group_ratio('x', x, y)
        ry = self._get_group_ratio('y', x, y)

        self.group_ratios[edi] = (rx,ry,grouping)

    def set_splitters_pos(self, grouping, *args):
        """args: (splitter_id, pos), (...), ...
        """

        spls = [*args]
        main_spl = self.l.spl_info(spls[0][0])

        target_splitters = {spl_id for spl_id,pos in spls}

        # add current position of unaffected splitters
        other_spls = [(spl_id,self.l.spl_info(spl_id)) for spl_id in SPLITTERS
                    if spl_id not in target_splitters   and   spl_id in LAYOUT_SPLITTERS[grouping]]
        spls += [(spl_id, spl.pos) for spl_id,spl in other_spls  if spl.isvert == main_spl.isvert]

        # move splitter to start
        for spl_id,_pos in spls:
            app_proc(PROC_SPLITTER_SET, (spl_id, 0))

        spls.sort()   # now haw all splitters in order

        # compress rightmost minimized
        prev_pos = main_spl.size
        prev_new = main_spl.size
        for i in range(len(spls)-1,-1,-1):
            spl_id,pos = spls[i]
            if prev_pos - pos > 30:
                break

            spls[i] = (spl_id, prev_new-10)
            prev_pos = pos
            prev_new = prev_new-10

        for spl_id,pos in spls:
            app_proc(PROC_SPLITTER_SET, (spl_id, pos)) # move splitter to start

        #pass; print(f'>>> applying spliters : {spls} =>   {[(spl_id, app_proc(PROC_SPLITTER_GET, spl_id)[2]) for spl_id in LAYOUT_SPLITTERS[grouping]]}')

    def load_splitters_ratios(self, grouping, ratios):
        resizes = []
        for spl_id,ratio in zip(SPLITTERS, ratios):
            if spl_id in LAYOUT_SPLITTERS[grouping]:
                spl = self.l.spl_info(spl_id)
                newpos = int(spl.size*ratio)
                resizes.append((spl_id, newpos))
        self.set_splitters_pos(grouping, *resizes)

    def focus_last_ed(self, *args, skip_group=None):
        l = Layout()
        geds = ((i,ed_group(i)) for i in range(6)  if skip_group is None or skip_group != i)
        timed_eds = [(ed.get_prop(PROP_ACTIVATION_TIME), ed, 'e'+str(i))  for i,ed in geds  if ed is not None]

        timed_eds.sort(key=lambda item: item[0], reverse=True)
        for _time, ed, gr_s in timed_eds:
            x,y,_item = next((x,y,item)  for x,y,item in l.enum_layout()  if item == gr_s)
            (w,spl_w),(h,spl_h) = l.get_ed_size('x', (x,y)), l.get_ed_size('y', (x,y))

            if (w == -1 or w > 30) and (h == -1 or h > 30):
                ed.focus()
                return True


    def _get_min_ax_layout(self, ax, minimized_group):

        if self.l.size(ax) == -1: # one high/wide - cant un-min
            return -1, None 

        l = self.l

        resizes = []
        work = list(l.enum_pairs(ax, l.x, l.y))
        min_edis = 'e'+str(minimized_group)

        ax_grs = l.enum_groups(ax=ax, ax_x=l.x, ax_y=l.y)
        group_sizes = [l.get_ed_size(ax, (x,y))[0] for x,y,gr_s in ax_grs]
        min_sizes = list(w for w in group_sizes  if w <= 30)
        gr_size, _spl_w = l.get_ed_size(ax, (l.x,l.y)) # current size of minimizeable group
        min_total_size = sum(min_sizes)
        
        if len(group_sizes) == 2  and  group_sizes[0] < 30: # first of two - minimized => minimize second
            x,y,spl_id = next(l.enum_spls(ax, ax_x=l.x, ax_y=l.y))
            newpos = l.size(ax) - 10
            resizes.append((spl_id,newpos))
        else: # normal
            prev_new, prev_old, spl_w = 0, 0, 0
            worksize = l.size(ax) - min_total_size - 4*len(work)
            for gr_s,spl_id,pos in work:
                if gr_s == min_edis: # minimizeable group
                    newpos = round(prev_new + 10)
                else: # other groups
                    edt = ed_group(int(gr_s[1:]))
                    axsize = pos - prev_old - spl_w
                    ratio = axsize/(worksize-(gr_size-10))

                    if axsize > 30: # not minimized
                        newpos = round(prev_new + (pos - prev_old + (gr_size-10)*ratio))
                    else: # minimized - keep size
                        newpos = round(prev_new + (pos - prev_old))
                resizes.append((spl_id,newpos)) # different format

                prev_new = newpos
                prev_old = pos
                spl_w = 4

        return resizes

    def _get_group_ratio(self, ax, x, y):
        spls = list(self.l.enum_spls(ax, ax_x=x, ax_y=y))
        spl_before = [spl_id  for sx,sy,spl_id in spls  if sx <= x and sy <= y]
        spl_after =  [spl_id  for sx,sy,spl_id in spls  if sx >= x and sy >= y]

        if not spl_before and not spl_after: # one editor high|wide layyuyt
            return -1

        ax_grs = self.l.enum_groups(ax=ax, ax_x=x, ax_y=y)
        group_sizes = (self.l.get_ed_size(ax, (x,y))[0] for x,y,gr_s in ax_grs)
        group_opened_sizes = [w for w in group_sizes  if w > 30]

        gr_size,spl_w = self.l.get_ed_size(ax, (x,y))

        average_width = sum(group_opened_sizes) / len(group_opened_sizes)
        r = gr_size / average_width
        commons = [1, 5/6, 0.75, 0.5, 1/3, 0.25, 1/6]
        for common in commons:
            delta = abs(r-common)
            if delta < common*0.04:
                r = common
                break

        return r # percent above 'average''

    def _prepare_resizes(self):
        l = self.l

        edw = sum(True for x,y,item in l.enum_layout(ax_y=l.y)  if item == l.edis)
        edh = sum(True for x,y,item in l.enum_layout(ax_x=l.x)  if item == l.edis)

        is_edge_l = l.x == 0
        is_edge_t = l.y == 0
        is_edge_r = l.x + edw == l.lw
        is_edge_b = l.y + edh == l.lh
        edgen = sum((is_edge_l, is_edge_t, is_edge_r, is_edge_b))
        iscorner = edgen == 2 and (is_edge_t != is_edge_b  and  is_edge_l != is_edge_r)

        resizes = [] # ('x'|'y', direction <-1, -0.5, +0.5, +1>)
        # corner - (is corner, 2 edges)                -- check if T-intersection | decide option        :: xy
        # between other in one row - 0.5 (not corner, 2 edges)  --  collapse sides  :: xx|yy
        # side no corner - (not corner, 1 edge)     -- collapse to side     :: x|y
        # side 2 corners - (not corner, 3 edges)    -- collapse to side     :: x|y
        if iscorner:
            if is_edge_t: resizes.append(('y', -1))
            if is_edge_b: resizes.append(('y', +1))
            if is_edge_l: resizes.append(('x', -1))
            if is_edge_r: resizes.append(('x', +1))
        else:
            if edgen == 2: # between others
                if l.lh == 1:
                    resizes = [('x', +0.5), ('x', -0.5)]
                else:
                    resizes = [('y', +0.5), ('y', -0.5)]
            else: # 1 or 3 edges
                if is_edge_t and (edgen == 1 or is_edge_l == is_edge_r): resizes.append(('y', -1))
                if is_edge_b and (edgen == 1 or is_edge_l == is_edge_r): resizes.append(('y', +1))
                if is_edge_l and (edgen == 1 or is_edge_t == is_edge_b): resizes.append(('x', -1))
                if is_edge_r and (edgen == 1 or is_edge_t == is_edge_b): resizes.append(('x', +1))

        resizes.sort()

        return resizes

    def _get_layout_splitters(self, x, y, dirx, diry):
        splx = 0
        sply = 0
        if dirx != 0:
            for i in range(1, self.l.lw):
                if type(self.l.layout[x+dirx*i][y]) == int: # found splitter
                    splx = x+dirx*i
                    break
        if diry != 0:
            for i in range(1, self.l.lh):
                if type(self.l.layout[x][y+diry*i]) == int: # found splitter
                    sply = y+diry*i
                    break
        return splx, sply

    def _get_splitters_ratios(self):
        spls = (self.l.spl_info(spl_id)  for spl_id in SPLITTERS)
        return [spl.pos/spl.size  for spl in spls]

class Layout:
    def __init__(self):
        self._spl_cache = {}

        self.grouping = app_proc(PROC_GET_GROUPING, '')
        self.gind = ed.get_prop(PROP_INDEX_GROUP)
        self.edis = 'e'+str(self.gind)

        self.layout = LAYOUTS[self.grouping]
        self.lw = len(self.layout)
        self.lh = len(self.layout[0])

        self.curpos = next((x,y)  for x,y,litem in self.enum_layout()  if litem == self.edis)
        self.x, self.y = self.curpos

    def enum_layout(self, ax=None, ax_x=None, ax_y=None):
        if ax is not None:
            ax_x,ax_y = (None,ax_y)  if ax == 'x' else  (ax_x,None)
        
        for x in range(self.lw):
            for y in range(self.lh):
                if (ax_x is not None and ax_x != x) or (ax_y is not None and ax_y != y):
                    continue
                yield (x, y, self.layout[x][y])

    def enum_spls(self, ax=None, ax_x=None, ax_y=None):
        return self._enum_type(int, ax, ax_x, ax_y)

    def enum_groups(self, ax=None, ax_x=None, ax_y=None):
        return self._enum_type(str, ax, ax_x, ax_y)

    def _enum_type(self, tp, ax=None, ax_x=None, ax_y=None):
        lgen = self.enum_layout(ax, ax_x=ax_x, ax_y=ax_y)
        
        gen = ((x,y,item)  for x,y,item in lgen  if type(item) == tp)
        if ax is not None  or  ((ax_x is None) != (ax_y is None)): # one row/col
            yield from gen
        # if not row - give unique items
        got = set()
        for x,y,item in gen:
            if item not in got:
                got.add(item)
                yield (x,y,item)
            
    def enum_pairs(self, ax, ax_x, ax_y):
        """returns ( (group, spl, spl_pos), ...)
            * last group is not included - has no splitter after it
        """
        gs = self.enum_groups(ax, ax_x, ax_y)
        ss = self.enum_spls(ax, ax_x, ax_y)
        yield from ((g[2], s[2], self.spl_info(s[2]).pos)  for g,s in zip(gs, ss))

    @property
    def vsize(self):  # groups' space dimensions px
        return self.size(ax='y')
    @property
    def hsize(self):  # groups' space dimensions px
        return self.size(ax='x')

    def size(self, ax): # test on 1-group size
        vert = ax == 'y'
        for _x,_y,spl_id in self.enum_spls():
            spl = self.spl_info(spl_id)
            if vert != spl.isvert and spl.isvis: # vertical splitter gives horizontal size
                return spl.size
        return 1

    def get_ed_size(self, ax, pos=None):
        x,y = self.curpos  if pos == None else  pos # default to current position

        vec = list(self.enum_layout(ax=ax, ax_x=x, ax_y=y))
        vecpos = x  if ax == 'x' else  y
        before = [item for x,y,item in vec[vecpos::-1]  if type(item) == int][0:1] # [firt splitter] before current
        after =  [item for x,y,item in vec[vecpos+1:]     if type(item) == int][0:1] # [first spl] after
        
        if not before and not after:
            return -1,-1

        if before:
            spl_w = 4
            start = self.spl_info(before[0]).pos
        else:
            spl_w = 0
            start = 0

        if after:
            end = self.spl_info(after[0]).pos
        else:
            end = self.size(ax=ax)

        return end-start,spl_w

    def spl_info(self, spl_id):
        if spl_id not in self._spl_cache:
            self._spl_cache[spl_id] = Splitter(app_proc(PROC_SPLITTER_GET, spl_id))
        return self._spl_cache[spl_id]

class Splitter:
    def __init__(self, t):
        self.isvert, self.isvis, self.pos, self.size = t

# [y][x] - convenient format to write, rotated to [x][y] next
LAYOUTS = { # grouping -> layout
    GROUPS_2VERT: [ ['e0', SPLITTER_G1, 'e1']],

    GROUPS_2HORZ: [ ['e0'],
                    [SPLITTER_G1],
                    ['e1']],

    GROUPS_3VERT: [ ['e0', SPLITTER_G1, 'e1', SPLITTER_G2, 'e2']],

    GROUPS_3HORZ: [ ['e0'],
                    [SPLITTER_G1],
                    ['e1'],
                    [SPLITTER_G2],
                    ['e2']],

    GROUPS_1P2VERT:[['e0', SPLITTER_G3, 'e1'],
                    ['e0', SPLITTER_G3, SPLITTER_G2],
                    ['e0', SPLITTER_G3, 'e2']],

    GROUPS_1P2HORZ:[['e0',          'e0',           'e0'],
                    [SPLITTER_G3,   SPLITTER_G3,    SPLITTER_G3],
                    ['e1',          SPLITTER_G2,    'e2']],

    GROUPS_4VERT: [ ['e0', SPLITTER_G1, 'e1', SPLITTER_G2, 'e2', SPLITTER_G3, 'e3']],

    GROUPS_4HORZ: [ ['e0'],
                    [SPLITTER_G1],
                    ['e1'],
                    [SPLITTER_G2],
                    ['e2'],
                    [SPLITTER_G3],
                    ['e3']],

    GROUPS_4GRID: [ ['e0',          SPLITTER_G1, 'e1'],
                    [SPLITTER_G3,   SPLITTER_G3, SPLITTER_G3],
                    ['e2',          SPLITTER_G1, 'e3']],
                    #['e2',          SPLITTER_G2, 'e3']], - G2 follows G1, so no need for it

    GROUPS_6VERT: [ ['e0', SPLITTER_G1, 'e1', SPLITTER_G2, 'e2', SPLITTER_G3, 'e3', SPLITTER_G4, 'e4', SPLITTER_G5, 'e5']],

    GROUPS_6HORZ: [ ['e0'],
                    [SPLITTER_G1],
                    ['e1'],
                    [SPLITTER_G2],
                    ['e2'],
                    [SPLITTER_G3],
                    ['e3'],
                    [SPLITTER_G4],
                    ['e4'],
                    [SPLITTER_G5],
                    ['e5']],

    GROUPS_6GRID: [ ['e0',          SPLITTER_G1, 'e1',          SPLITTER_G2, 'e2'],
                    [SPLITTER_G3,   SPLITTER_G3, SPLITTER_G3,   SPLITTER_G3, SPLITTER_G3],
                    ['e3',          SPLITTER_G1, 'e4',          SPLITTER_G2, 'e5']],
}

# set() of visible splitters for layouts; splitter's 'is_visible' property is problematic for this
LAYOUT_SPLITTERS = {}

# transposing from [y][x] to [x][y]
for l in LAYOUTS.values():
    w = len(l) # h in new
    h = len(l[0]) # w in new
    copy = [*l]
    l.clear()
    for y in range(h): # new w -- x
        l.append([copy[x][y]  for x in range(w)]) # new columns

# fill LAYOUT_SPLITTERS
for grouping,layout in LAYOUTS.items():
    splitters = set()
    for column in layout:
        for item in column:
            if type(item) == int:
                splitters.add(item)

    LAYOUT_SPLITTERS[grouping] = splitters