"""قواعد الكلمات (regex) اللي بتفلتر الإعلانات."""
import re
from jb_config import NL

JOB_WORDS = re.compile(
    r"warehouse|lager|magazijn|magasin|magazzin|magazyn|production|produktion|productie|"
    r"produkc|factory|fabrik|packer|packing|pack|verpack|picker|kommission|préparateur|general worker|helfer|"
    r"helper|cleaner|reinigung|schoonmaak|nettoyage|sprz[aą]t|pulizie|kitchen|küche|farm|agricult|landwirt|"
    r"harvest|construction|housekeeping|manutention|operaio|operai|loader|unloading|logisti|stock|storekeeper|"
    r"material|opérateur|medewerker|mitarbeiter|pracownik|labourer|laborer|packaging|"
    r"عامل|مخزن|مستودع|إنتاج|انتاج|تعبئة|تغليف|تنظيف|زراعة|حصاد", re.I)

FEE = re.compile(r"registration fee|placement fee|processing fee|pay (a|the) fee|vermittlungsgeb[üu]hr|"
    r"geb[üu]hr f[üu]r die vermittlung", re.I)
RESIDENCY = re.compile(
    r"must (already )?(have|hold) (a )?(valid )?(eu |european )?(work permit|right to work)|"
    r"right to work in|eu citizens? only|eu/eea (citizen|national)|already (living|residing|based) in|"
    r"must (be|live) (a )?resident|valid residence permit|eu passport|"
    r"arbeitserlaubnis (erforderlich|vorhanden|nachweisen)|wohnsitz in (deutschland|österreich) (erforderlich|vorausgesetzt)|"
    r"werkvergunning (is )?(vereist|verplicht)|inwoner van", re.I)
LANG = re.compile(r"fließend(e|es)? deutsch|deutsch (auf )?(muttersprach|c1|c2)|vloeiend nederlands|"
    r"moedertaal nederlands|fran[cç]ais courant|langue maternelle fran|biegła znajomość|madrelingua italian", re.I)
SPONSOR = re.compile(
    r"visa sponsor|sponsor(ship)? (a )?(work )?(visa|permit)|sponsor your (visa|work permit)|"
    r"work permit (provided|arranged|assistance|support|sponsorship)|work visa provided|"
    r"we (arrange|organi[sz]e|handle|obtain|apply for|provide|cover|pay for) .{0,35}(visa|work permit)|"
    r"visumhilfe|wir (übernehmen|kümmern uns um) .{0,30}(visum|arbeitserlaubnis)|arbeitserlaubnis (wird|übernehmen)|"
    r"werkvergunning (regelen|aanvragen|verzorgen)|wij (regelen|verzorgen) .{0,30}(visum|werkvergunning)|"
    r"permesso di lavoro (fornito|garantito|incluso|a carico)|"
    r"(ci occupiamo|ti aiutiamo|supportiamo|assistiamo|forniamo) .{0,30}(permesso|visto)|"
    r"nous (nous occupons|fournissons|prenons en charge) .{0,30}(permis|visa)|zapewniamy .{0,25}(zezwolenie|wiz)",
    re.I)
# كلمة "work permit" أو "permesso di lavoro" لوحدها مش دليل إن صاحب العمل بيوفرها.
ABROAD = re.compile(r"from abroad|outside (of )?(the )?(eu|europe)|non-eu|third[- ]country|international (candidates|applicants)|"
    r"aus dem ausland|drittstaat|uit het buitenland|de l'étranger|z zagranicy|dall'estero", re.I)
RELOC = re.compile(r"relocation|relocate|worldwide", re.I)  # إشارة ضعيفة: ممكن تكون نقل داخلي
HOUSING = re.compile(r"accommodation|housing (provided|included)|free (housing|lodging)|unterkunft|wohnung gestellt|"
    r"huisvesting|logement fourni|hébergement|zakwaterowanie|alloggio", re.I)
HEDGE = re.compile(r"\b(may|might|could|can be|possible|possibly|potentially|if (needed|required|eligible|applicable|selected)|"
    r"subject to|depending|case[- ]by[- ]case|in some cases|for some (roles|positions)|selected candidates|where possible|"
    r"sometimes|eventually|può|potrebbe|possibile|eventuale|in alcuni casi|kann|könnte|möglich|eventuell|"
    r"mogą|może|możliwe|w niektórych|peut|pourrait)\b", re.I)
REQ_PERMIT = re.compile(
    r"(work permit|permesso di lavoro|permis de travail|zezwolenie na pracę|arbeitserlaubnis|werkvergunning)\W{0,3}"
    r"(is |è |est |jest |ist )?(required|needed|necessary|mandatory|richiest[oa]|necessari[oa]|obbligatori[oa]|"
    r"requis|requise|obligatoire|wymagane|erforderlich|vereist|verplicht)|"
    r"(valid|existing|current|own) (work permit|permesso di lavoro|permis de travail)", re.I)
NEG = re.compile(
    r"\bno\W+(visa\W+|work permit\W+)?sponsor|\bno\W+(visa|work permit)\b|without (a )?(visa|sponsorship)|"
    r"(do|does|did) not (offer|provide|sponsor|arrange)|(don't|doesn't|cannot|can't|unable to) (offer|provide|sponsor|arrange)|"
    r"not (able|in a position) to (offer|provide|sponsor)|"
    r"(visa|sponsorship|work permit)s? (is |are )?(not|un)\W?(available|provided|offered|possible|included)|"
    r"(not|never) require(s|d)? (visa |work permit )?sponsorship|"
    r"keine (visa|arbeitserlaubnis|sponsor)|geen (visum|werkvergunning)|senza (visto|permesso|sponsor)|bez (wizy|sponsoringu)",
    re.I)

SENT_RE = re.compile("[^.!?" + NL + "]+[.!?]?")
