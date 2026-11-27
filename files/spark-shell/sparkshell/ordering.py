"""Order logic for dragging, kept free of GTK so tests can run it: where a dropped item goes, how
a saved order is merged with what is there now, and what a task-list drop does to the pinned list."""


def merge_order(saved, current, ident=lambda x: x):
    """`current` items sorted by their place in `saved`; items saved never mentioned keep their
    current order and go at the end. `ident` maps an item to the id stored in `saved`."""
    rank = {}
    for i, key in enumerate(saved or []):
        rank.setdefault(key, i)
    known = [x for x in current if ident(x) in rank]
    known.sort(key=lambda x: rank[ident(x)])        # stable: duplicates keep their order
    return known + [x for x in current if ident(x) not in rank]


def move_key(keys, src, dst, after):
    """`keys` with `src` taken out and put before `dst` (or after it when `after`). When `dst` is
    None or missing, `src` goes to the end. `src` may be absent from `keys` (dragged in from
    another screen's task list)."""
    out = [k for k in keys if k != src]
    if dst is None or dst == src or dst not in out:
        if dst == src and src in keys:
            return list(keys)
        out.append(src)
        return out
    at = out.index(dst) + (1 if after else 0)
    out.insert(at, src)
    return out


def reorder_tasks(keys, pinned, src, dst, after, pinnable=True):
    """A task button was dropped. `keys` is the order shown (pinned first), `pinned` the saved
    list. Returns (new_pinned, loose_order).

    Pinned apps stay pinned: dropped past the last pinned one, an app goes to the end of the
    pinned group. An unpinned app dropped before or between pinned ones becomes pinned there
    (when it has a desktop entry, `pinnable`); dropped among the unpinned it only moves, and the
    order is remembered for the session. Pinned entries whose app is not installed (not in
    `keys`) are kept at the end of the pinned list."""
    new = move_key(keys, src, dst, after)
    pinned_set = set(pinned)
    last = max((i for i, k in enumerate(new) if k in pinned_set and k != src), default=-1)
    at = new.index(src)
    if src not in pinned_set:
        if pinnable and at < last:
            pinned_set.add(src)
        elif at <= last:                  # cannot sit among pinned ones: just after them
            new.remove(src)
            new.insert(last, src)
    new_pinned = [k for k in new if k in pinned_set]
    # pinned apps are drawn first, so a pinned app is shown in the pinned group wherever it fell
    new_pinned += [k for k in pinned if k not in new_pinned]
    loose = [k for k in new if k not in set(new_pinned)]
    return new_pinned, loose
