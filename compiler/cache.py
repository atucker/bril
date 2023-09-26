import cfg
import dominators

BLOCKS = 'blocks'
SUCCESSORS = 'successors'
PREDECESSORS = 'predecessors'
DOM = 'dom'


def func_ensure_analysis(func, analysis, key_or_keys):
    """
    Return a type of analysis, and compute it + cache its prereqs if needed

    Side effects:
        Mutates analysis dict by adding analyses
    """
    if isinstance(key_or_keys, str):
        key = key_or_keys
        assert key in {BLOCKS, SUCCESSORS, PREDECESSORS, DOM}
        if key == BLOCKS and BLOCKS not in analysis:
            blocks, successors = cfg.make_func_cfg(func)
            analysis[BLOCKS] = blocks
            analysis[SUCCESSORS] = successors
        elif key == SUCCESSORS and SUCCESSORS not in analysis:
            blocks, successors = cfg.make_func_cfg(func)
            analysis[BLOCKS] = blocks
            analysis[SUCCESSORS] = successors
        elif key == PREDECESSORS and PREDECESSORS not in analysis:
            analysis[PREDECESSORS] = cfg.get_predecessors(
                func_ensure_analysis(func, analysis, SUCCESSORS)
            )
        elif key == DOM and DOM not in analysis:
            analysis[DOM] = dominators.make_dominators(
                func_ensure_analysis(func, analysis, SUCCESSORS)
            )
        return analysis[key]
    else:
        keys = key_or_keys
        return [func_ensure_analysis(func, analysis, key) for key in keys]
