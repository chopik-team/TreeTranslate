import re
from app.documents.pdf_fidelity import faithful_result,FidelityMismatch
from app.translation_memory.normalization import compatible
from .errors import ConstraintFailure
from .normalization import normalize,boundary

# Validation vocabulary only; never used to replace or inflect terminology.
SI_UNITS={'kg':'kg','mm':'mm','cm':'cm','kPa':'kPa','MPa':'MPa','Nm':'Nm','V':'V','W':'W','kW':'kW','°C':'°C','°F':'°F'}
WORD_UNITS={
    'liter':'L','liters':'L','litre':'L','litres':'L','l':'L','л':'L','литр':'L','литра':'L','литров':'L','升':'L',
    'gallon':'gal','gallons':'gal','gal':'gal','галлон':'gal','галлона':'gal','галлонов':'gal',
    'мм':'mm','миллиметр':'mm','миллиметра':'mm','миллиметров':'mm','毫米':'mm',
    'см':'cm','厘米':'cm','кг':'kg','千克':'kg','公斤':'kg','кпа':'kPa','мпа':'MPa','вт':'W','квт':'kW',
    'rpm':'rpm','об/мин':'rpm','cc':'cc','см³':'cc','cm³':'cc'}
UNIT_RE=re.compile(r'\d+(?:[.,]\d+)?\s*('+ '|'.join(re.escape(u) for u in sorted(SI_UNITS,key=len,reverse=True))+
                   r'|(?i:'+ '|'.join(re.escape(u) for u in sorted(WORD_UNITS,key=len,reverse=True))+r'))(?![A-Za-zА-Яа-я])')


def units(text):
    return tuple(SI_UNITS.get(m.group(1),WORD_UNITS.get(m.group(1).casefold())) for m in UNIT_RE.finditer(text))


def forbidden_found(text,terms):
    normalized=normalize(text,fold=True)
    for term in terms:
        term=normalize(term,fold=True)
        for match in re.finditer(re.escape(term),normalized):
            if boundary(normalized,match.start(),match.end(),term):return True
    return False


def validate_result(source,target,forbidden=()):
    try:target=faithful_result(source,target)
    except (FidelityMismatch,ValueError):raise ConstraintFailure('fidelity') from None
    if not compatible(source,target):raise ConstraintFailure('protected_atom')
    if units(source)!=units(target):raise ConstraintFailure('unit_fidelity')
    if forbidden_found(target,forbidden):raise ConstraintFailure('forbidden_target')
    return target
