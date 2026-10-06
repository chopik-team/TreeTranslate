def rank(match,domain):
    entry=match.entry
    return (match.store=='user' and entry.status=='CONFIRMED', entry.domain==domain, entry.priority,
            match.end-match.start,entry.trust,-entry.id,match.store)


def resolve(matches,domain):
    accepted=[]
    for match in sorted(matches,key=lambda m:rank(m,domain),reverse=True):
        if not any(match.start<m.end and m.start<match.end for m in accepted):accepted.append(match)
    return tuple(sorted(accepted,key=lambda m:(m.start,m.end)))
