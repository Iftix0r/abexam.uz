#!/usr/bin/env python3
"""Build IELTS Full Mock Tests 17 and 18 from the source pack in TESTLAR/13.

The pack holds two full sets: two listening booklets with their audio, six
reading passages (two of each passage number), two Task 1 charts and two
Task 2 prompts.  Neither listening booklet carries an answer key, so the
listening answers below were taken from the recordings. The audio is
re-encoded to 128 kbps as listening17.mp3 / listening18.mp3 (the 320 kbps
originals stay out of git, like the rest of the raw pack).  Two of the reading
PDFs ("The Importance of Business Cards", "Book Review: Slowness") are photo
scans without a text layer, so their passages are transcribed here.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TESTLAR" / "13"
DATA = ROOT / "data" / "cambridge"
IMAGES = DATA / "images"

TFNG = [(x, x.title()) for x in ("TRUE", "FALSE", "NOT GIVEN")]
YNNG = [(x, x.title()) for x in ("YES", "NO", "NOT GIVEN")]


def options(items):
    return [{"key": str(key), "text": text} for key, text in items]


def question(order, text, answer, choices=(), kind=None, word_limit=0):
    return {
        "order": order,
        "text": text,
        "question_type": kind or ("mcq" if choices else "gap_fill"),
        "correct_answer": str(answer),
        "options": options(choices),
        "explanation": "",
        "word_limit": word_limit,
        "model_answer": "",
    }


def add(qs, first, prompts, answers, heading="", choices=(), kind=None):
    """Append a run of questions numbered from `first`; the group heading
    ("[Title] Instructions") goes on the first one only."""
    for offset, (prompt, answer) in enumerate(zip(prompts, answers)):
        prefix = heading + "\n" if heading and offset == 0 else ""
        qs.append(question(first + offset, prefix + prompt, answer, choices, kind))


def choose_two(qs, first, heading, answer, choices):
    # Both rows carry the same "X/Y" answer: grade_answers() accepts the two
    # letters in either order and never counts the same letter twice.
    qs.append(question(first, heading, answer, choices))
    qs.append(question(first + 1, "Select the second answer.", answer, choices))


def pdf_text(name):
    return subprocess.check_output(
        ["pdftotext", "-layout", str(SOURCE / name), "-"], text=True
    ).replace("\f", "\n")


def clean(text):
    text = re.sub(r"(?<=\w)- (?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def blocks(raw):
    """Paragraphs separated by blank lines.  A page break also leaves a blank
    line, even mid-sentence, so a block that does not end a sentence is
    joined to the next one."""
    out = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l.strip() for l in block.splitlines() if l.strip() and not re.fullmatch(r"\d+", l.strip())]
        text = clean(" ".join(lines))
        if not text:
            continue
        if out and not re.search(r"[.?!:'’\")]$", out[-1]):
            out[-1] = clean(out[-1] + " " + text)
        else:
            out.append(text)
    return out


def plain_passage(title, raw, subtitle=""):
    """Paragraphs separated by blank lines in the PDF."""
    out = [f"<h2>{html.escape(title)}</h2>"]
    if subtitle:
        out.append(f"<p><em>{html.escape(subtitle)}</em></p>")
    for text in blocks(raw):
        out.append(f"<p>{html.escape(text)}</p>")
    return "".join(out)


def lettered_passage(title, raw, letters, intro=""):
    """Paragraphs that start with a section letter (A, B, ...) at the left
    margin.  Page breaks in these PDFs can fall between paragraphs without a
    blank line, so split on the letters rather than on blank lines."""
    pattern = rf"^\s*([{letters}])\s+(?=[A-Z'‘])"
    parts = re.split(pattern, raw.strip(), flags=re.M)
    out = [f"<h2>{html.escape(title)}</h2>"]
    if intro:
        out.append(f"<p><em>{html.escape(intro)}</em></p>")
    for letter, body in zip(parts[1::2], parts[2::2]):
        # A blank line inside a section is a second paragraph of it.
        for n, text in enumerate(blocks(body)):
            label = f"<strong>{letter}</strong>&nbsp;&nbsp;" if n == 0 else ""
            out.append(f"<p>{label}{html.escape(text)}</p>")
    return "".join(out)


def between(text, start, end):
    i = text.index(start) + len(start)
    return text[i:text.index(end, i)]


# --------------------------------------------------------------------------
# Mock Test 17: Listening 3 + Seaweed / Public Art / The Long Road to AI
# --------------------------------------------------------------------------

def listening17():
    qs = []
    add(qs, 1, [
        "Basic cabin: kitchen has a fridge and a ___",
        "Standard cabin: located close to the ___",
        "Standard cabin: fully-equipped kitchen and a ___",
        "Standard Plus cabin: facing the ___",
        "Standard Plus cabin: discount of ___% for bookings over ten nights",
    ], ["microwave", "reception", "shower", "lake", "18/eighteen"],
        "[Ohope Holiday Park: Accommodation] Complete the table. Write ONE WORD AND/OR A NUMBER for each answer.")
    add(qs, 6, [
        "The children can play ___ for free.",
        "It's possible to hire equipment for ___ for an afternoon.",
        "The children could visit the local ___ on Saturday and Sunday.",
        "There are guided tours of the ___ every evening to see the birds.",
        "Contact ___ to confirm the booking.",
    ], ["tennis", "fishing", "farm", "forest", "Arataki"],
        "[General information about the holiday park and the Ohope area] Complete the notes. Write ONE WORD ONLY for each answer.")

    add(qs, 11, ["Joan normally gets up at"], ["B"],
        "Choose the correct letter, A, B or C.", [("A", "5.30 a.m."), ("B", "6.30 a.m."), ("C", "7.30 a.m.")])
    add(qs, 12, ["Joan's first task of the day is to"], ["B"],
        choices=[("A", "clean the horses."), ("B", "organize her son."), ("C", "do farm work.")])
    add(qs, 13, [
        "In her local district there are at present twenty-two riders and ___ helpers on the volunteer list,",
        "out of whom ___ come regularly.",
    ], ["40/forty", "25/twenty-five"],
        "[Riding for the Disabled (RDA)] Complete the summary. Write ONE WORD AND/OR A NUMBER for each answer.")
    like = [("A", "She really likes it."), ("B", "She doesn't mind it."), ("C", "She hates it.")]
    add(qs, 15, ["correspondence", "fund-raising", "calling riders", "organizing accounts"], "BCAC",
        "How much does Joan like doing each of the following activities? Write the correct letter, A, B or C.",
        like, "matching")
    choose_two(qs, 19, "Choose TWO letters, A-E.\nJoan says the TWO ways the RDA needs to improve are by", "B/E", [
        ("A", "giving special training."), ("B", "making fund-raising more effective."),
        ("C", "opening more RDA centres."), ("D", "providing more helpers."),
        ("E", "recognizing difficulties of disabled riders."),
    ])

    choose_two(qs, 21, "Choose TWO letters, A-E.\nWhat do the speakers agree are the TWO reasons why children play outdoors less now than in the past?", "A/E", [
        ("A", "concerns about traffic"), ("B", "limited outdoor play facilities"),
        ("C", "increased time spent online"), ("D", "preference for indoor play"),
        ("E", "reduction in free time"),
    ])
    choose_two(qs, 23, "Choose TWO letters, A-E.\nIn his assignment, which TWO aspects of outdoor play does Ravi want to focus on?", "A/D", [
        ("A", "how it helps children to evaluate risk"), ("B", "how it broadens their horizons"),
        ("C", "how it aids children's muscular development"), ("D", "how it improves children's digestion"),
        ("E", "how it teaches children about the environment"),
    ])
    choose_two(qs, 25, "Choose TWO letters, A-E.\nAccording to Ravi, in which TWO ways are children's periods of outdoor play now different from a generation ago?", "C/D", [
        ("A", "They are less dangerous."), ("B", "They involve fewer children."),
        ("C", "They usually last a shorter time."), ("D", "They include fewer made-up games."),
        ("E", "They involve fewer chasing games."),
    ])
    mcqs = [
        ("Ravi thinks parents should be more concerned about the decline of outdoor play because", "B",
         [("A", "it affects family relationships."), ("B", "it leads to health problems later in life."), ("C", "it makes childhood less enjoyable.")]),
        ("What does Ravi say that schools should do with regard to outdoor play?", "A",
         [("A", "revise their aims"), ("B", "spend more money on it"), ("C", "listen to the views of parents")]),
        ("What did Smith and Barker say about children in rural areas?", "A",
         [("A", "They tend not to be allowed on farmland."), ("B", "They receive more supervision out of doors."), ("C", "They spend more time outdoors than city children.")]),
        ("What problem does Dr Chang highlight about Smith and Barker's research?", "C",
         [("A", "Its findings are inconclusive."), ("B", "It is too old to be useful."), ("C", "Its focus is limited.")]),
    ]
    for offset, (prompt, answer, choices) in enumerate(mcqs):
        prefix = "Choose the correct letter, A, B or C.\n" if offset == 0 else ""
        qs.append(question(27 + offset, prefix + prompt, answer, choices))

    add(qs, 31, [
        "Aim in UK is to reduce carbon emissions from energy consumed in ___ by approximately 25%",
        "Most popular 'green' energy: ___",
        "Little investment in heat pumps in UK due to lack of ___ in using them",
        "Heat pumps serve the same purpose as a ___",
        "Most heat pumps get heat from the earth or the ___",
        "Water is heated to 60°C to destroy ___",
        "Central heating systems monitored: ___ and under-floor heating",
        "Installation: need to provide improved ___ in pump-fitting technique",
        "___ designs performed best",
        "Need for a ___ to co-ordinate the installation",
    ], ["homes", "solar", "experience", "boiler", "air", "bacteria", "radiators", "training", "simple", "supervisor"],
        "[Field trial – heat pump technology] Complete the notes. Write ONE WORD ONLY for each answer.")
    return qs


def listening17_notes():
    return {
        "1": """<div class="notes-table-wrap"><table class="notes-table">
<tr><th>Type of cabin</th><th>Location</th><th>Facilities</th><th>Cost and charges</th></tr>
<tr><td>Basic</td><td>next to the pool</td><td>kitchen has a fridge and a [[1]]</td><td>$35 per night</td></tr>
<tr><td>Standard</td><td>close to [[2]]</td><td>fully-equipped kitchen and a [[3]]</td><td>$55 per night</td></tr>
<tr><td>Standard Plus</td><td>facing the [[4]]</td><td>comes with own spa</td><td>discount of [[5]]% for bookings over ten nights</td></tr>
</table></div>""",
        "6": """<ul>
<li>The children can play [[6]] for free.</li>
<li>It's possible to hire equipment for [[7]] for an afternoon.</li>
<li>The children could visit the local [[8]] on Saturday and Sunday.</li>
<li>There are guided tours of the [[9]] every evening to see the birds.</li>
<li>Contact [[10]] to confirm the booking.</li>
</ul>""",
        "13": """<p>Joan's official title in Riding for the Disabled (RDA) is chairperson. In her local district there are at present twenty-two riders and [[13]] helpers on the volunteer list, out of whom [[14]] come regularly.</p>""",
        "31": """<p><strong>Background</strong></p>
<ul>
<li>Aim in UK is to reduce carbon emissions from energy consumed in [[31]] by approximately 25%</li>
<li>Most popular 'green' energy: [[32]]</li>
<li>Little investment in heat pumps in UK due to lack of [[33]] in using them</li>
</ul>
<p><strong>What is a heat pump?</strong></p>
<ul>
<li>Heat pumps serve the same purpose as a [[34]]</li>
<li>Most heat pumps get heat from the earth or the [[35]]</li>
<li>Water is heated to 60°C to destroy [[36]]</li>
</ul>
<p><strong>The field trial</strong></p>
<ul>
<li>83 sites across the UK</li>
<li>Central heating systems monitored: [[37]] and under-floor heating</li>
</ul>
<p><strong>Key conclusions</strong></p>
<ul>
<li>Installation: need to provide improved [[38]] in pump-fitting technique</li>
<li>[[39]] designs performed best</li>
<li>Customers needed to be told about regulating the controls</li>
<li>Need for a [[40]] to co-ordinate the installation</li>
</ul>""",
    }


def reading17_content():
    seaweed = pdf_text("Passage 1 Seaweed copy.pdf")
    seaweed = seaweed.split("Seaweed\n", 1)[1].split("Questions 1", 1)[0]

    art = pdf_text("Passage 2 Public Art Programs Research Update.pdf")
    art = between(art, "Public Art Programs: Research Update", "Questions 20")
    intro, art = art.split("A    Researcher", 1)
    art = "A    Researcher" + art

    ai = pdf_text("Passage 3 The Long Road to Artificial Intelligence.pdf")
    ai = between(ai, "The Long Road to Artificial Intelligence", "Questions 27")
    return (
        plain_passage("Seaweed", seaweed)
        + lettered_passage("Public Art Programs: Research Update", art, "A-F", clean(intro))
        + plain_passage("The Long Road to Artificial Intelligence", ai)
    )


def reading17():
    qs = []
    add(qs, 1, [
        "Seaweed has been used to feed animals on some Scottish islands for thousands of years.",
        "In the 8th century in Japan, eating seaweed was reserved for special occasions.",
        "The findings at Monte Verde revealed new information about the significance of women's roles in prehistoric times.",
        "Potash was Norway's largest export in the 1800s.",
        "Dr Kathleen Drew-Baker is more famous in Japan than she is in the UK.",
    ], ["TRUE", "FALSE", "TRUE", "NOT GIVEN", "TRUE"],
        "[Seaweed] Do the following statements agree with the information given in Reading Passage 1? Write TRUE, FALSE or NOT GIVEN.",
        TFNG)
    add(qs, 6, [
        "was destroyed by pollution and ___ in 1948",
        "recovered as a result of Kathleen Drew-Baker's research into ___, a seaweed species similar to nori",
        "new methods have resulted in the type of seaweed called ___ becoming a successful crop",
        "has provided an alternative source of income for ___",
        "may be used to minimise the harmful effects of various ___ produced by different industries",
        "the cost of production and shortage of ___ may be preventing growth of the industry in Europe",
        "could create very large numbers of new ___",
        "could be used instead of oil to power a small percentage of ___",
    ], ["typhoons", "laver", "kelp", "fishermen/New England fishermen", "chemicals", "markets", "jobs", "vehicles"],
        "Complete the notes below. Choose NO MORE THAN THREE WORDS from the passage for each answer.")

    headings = [(n, t) for n, t in zip(
        ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii"], [
            "Interpreting the research behind who is participating in art activities",
            "How sales of artwork have increased in many countries",
            "Two opportunities for getting kids involved in art activities",
            "How art can be made accessible to the public",
            "Developing a model to explain the lack of participation in art",
            "The connection between art and media",
            "How involvement with art affects well-being and attitudes",
            "How art makes communities safer and more vital",
        ])]
    add(qs, 14, [f"Section {c}" for c in "ABCDEF"], ["vii", "viii", "iv", "v", "i", "iii"],
        "[Public Art Programs: Research Update] Choose the correct heading for each section from the list of headings.",
        headings, "matching")
    researchers = [(c, n) for c, n in zip("ABCDEF", ["Spector", "Oliphant", "Riley", "Hughes", "Bradshaw", "Yoshitomi"])]
    add(qs, 20, [
        "Art activities can contribute to lowering negative incidents associated with juvenile crime.",
        "Art can bring money and visitors into a community.",
        "Commercial interests are drawn to areas that emphasise public art.",
        "Art activities can both energise and calm people.",
    ], "ADCB", "Match each statement with the correct researcher, A–F.", researchers, "matching")
    add(qs, 24, [
        "Sometimes people want to get involved in art activities but can't afford it, can't fit it into their schedule, or don't have the suitable ___",
        "A noticeable correlation exists between art involvement in childhood and those in ___",
        "The National Photography Program allows members to grow personally and also gain ___",
    ], ["attire", "adults/adulthood", "recognition"],
        "Complete the sentences below. Choose ONE WORD ONLY from the passage for each answer.")

    mcqs = [
        ("When playing chess against the computer Deep Blue, Kasparov felt that it", "D", [
            ("A", "had been programmed to predict his moves."), ("B", "was able to see into his own thought processes."),
            ("C", "used powers that were potentially dangerous to humans."), ("D", "was fundamentally different from others he had encountered.")]),
        ("What is the writer's main idea in the third paragraph?", "C", [
            ("A", "In the last 50 years machines have advanced more quickly than expected."),
            ("B", "There are certain features of chess that machines cannot replicate."),
            ("C", "Skill at chess is more significant than other machine achievements."),
            ("D", "Machines will always be more successful at some tasks than at others.")]),
        ("The writer describes the case of an office worker to illustrate the point that", "A", [
            ("A", "everyday human actions involve a complex combination of skills."),
            ("B", "some types of mechanical activities require little conscious thought."),
            ("C", "some people are able to carry out multiple tasks at the same time."),
            ("D", "certain human tasks are more intellectually demanding than others.")]),
        ("In the fifth paragraph, the writer claims that", "C", [
            ("A", "ideas of what success means vary across cultures."), ("B", "machines are most effective at game-like activities."),
            ("C", "machines are better at specialization than at adaptation."),
            ("D", "it may be impossible to isolate different skills involved in an activity.")]),
    ]
    for offset, (prompt, answer, choices) in enumerate(mcqs):
        prefix = "[The Long Road to Artificial Intelligence] Choose the correct letter, A, B, C or D.\n" if offset == 0 else ""
        qs.append(question(27 + offset, prefix + prompt, answer, choices))
    words = [(c, w) for c, w in zip("ABCDEFGHIJ", [
        "results", "nourishment", "basis", "qualities", "protection",
        "evolution", "surroundings", "values", "perception", "movement"])]
    add(qs, 31, [
        "a brain which has evolved to provide ... for that body",
        "senses provide it with information about its ...",
        "it can react physically to what it ... through senses",
        "a link between ... and action",
        "The ... which make us human",
        "have their ... in this link between the brain and the body",
    ], "EGJIDC", "[Embodiment: an essential feature] Complete the summary using the list of words, A-J.", words, "matching")
    add(qs, 37, [
        "Any sort of artificial general intelligence must have the capacity for metabolism and reproduction.",
        "Intelligence may depend on the ability to interact with a complex and unpredictable environment.",
        "It is dangerous to rely too much on multi-specialist robots which could develop unfixable faults.",
        "Training by experts is essential for acquiring certain types of skills.",
    ], ["NO", "YES", "NOT GIVEN", "NOT GIVEN"],
        "Do the following statements agree with the claims of the writer? Write YES, NO or NOT GIVEN.", YNNG)
    return qs


def reading17_notes():
    return {
        "6": """<h5>Japanese seaweed industry</h5>
<ul><li>was destroyed by pollution and [[6]] in 1948</li>
<li>recovered as a result of Kathleen Drew-Baker's research into [[7]], a seaweed species similar to nori</li></ul>
<h5>Seaweed farming in the USA</h5>
<ul><li>new methods have resulted in the type of seaweed called [[8]] becoming a successful crop</li>
<li>has provided an alternative source of income for [[9]]</li></ul>
<h5>Seaweed production in the future</h5>
<ul><li>may be used to minimise the harmful effects of various [[10]] produced by different industries</li>
<li>the cost of production and shortage of [[11]] may be preventing growth of the industry in Europe</li>
<li>could create very large numbers of new [[12]]</li>
<li>could be used instead of oil to power a small percentage of [[13]]</li></ul>""",
        "24": """<div class="pdf-summary summary-sentences">
<p>Sometimes people want to get involved in art activities but can't afford it, can't fit it into their schedule, or don't have the suitable [[24]].</p>
<p>A noticeable correlation exists between art involvement in childhood and those in [[25]].</p>
<p>The National Photography Program allows members to grow personally and also gain [[26]].</p>
</div>""",
        "31": """<p>Unlike machines, animals (including humans) have a body, including a brain which has evolved to provide [[31]] for that body and allow its genes to be passed on. An animal's senses provide it with information about its [[32]], and then it can react physically to what it [[33]] through senses. The interaction of the body and brain therefore allows the creation of a link between [[34]] and action. The [[35]] which make us human and which distinguish us from animals have their [[36]] in this link between the brain and the body, and have developed from it.</p>
<div class="summary-word-bank">
<span><strong>A</strong> results</span><span><strong>B</strong> nourishment</span><span><strong>C</strong> basis</span><span><strong>D</strong> qualities</span>
<span><strong>E</strong> protection</span><span><strong>F</strong> evolution</span><span><strong>G</strong> surroundings</span><span><strong>H</strong> values</span>
<span><strong>I</strong> perception</span><span><strong>J</strong> movement</span>
</div>""",
    }


# --------------------------------------------------------------------------
# Mock Test 18: TEST 6 (JF) + Business Cards / Nanotechnology / Slowness
# --------------------------------------------------------------------------

def listening18():
    qs = []
    add(qs, 1, [
        "Located in ___ Street,", "next to the ___", "Saturdays: open until ___ p.m.",
        "a ___ club (5–13 year olds)", "a ___ club (every other Saturday)",
        "Can meet local ___ (about once a year)", "Can borrow ___",
        "Various ___ are available", "Can drop off books via the letter box (must give card ___)",
        "Library shop sells ___ (wide range)",
    ], ["Skellarn", "park", "4.30/4:30", "drama", "singing", "artists", "films", "magazines", "number", "maps"],
        "[Library services] Complete the notes. Write ONE WORD AND/OR A NUMBER for each answer.")
    mcqs = [
        ("What improvement has recently been made to the company's fire notices?", "B", [
            ("A", "Their wording has been simplified."), ("B", "Their visuals are now clearer."), ("C", "They are now more effectively displayed.")]),
        ("The health and safety inspectors identified a problem with office", "B", [
            ("A", "layout."), ("B", "tidiness."), ("C", "seating.")]),
        ("What impressed the inspectors with regard to the company's computer screens?", "C", [
            ("A", "how often employees take breaks from their screens"), ("B", "how often staff using the screens had eye tests"),
            ("C", "how often assessments of the screens were carried out")]),
        ("The inspectors agreed with management that protective clothing for staff", "A", [
            ("A", "is currently suitable."), ("B", "requires some adaptation."), ("C", "must be paid for by the company.")]),
        ("The inspectors suggested more training is required in", "A", [
            ("A", "identifying hazards."), ("B", "reporting hazards."), ("C", "preventing hazards.")]),
        ("Next month's first aid training course is aimed at staff who", "C", [
            ("A", "have already undertaken a first aid course."), ("B", "are in charge of a particular department."),
            ("C", "have little previous first aid training.")]),
    ]
    for offset, (prompt, answer, choices) in enumerate(mcqs):
        prefix = "[Update on health and safety issues] Choose the correct letter, A, B or C.\n" if offset == 0 else ""
        qs.append(question(11 + offset, prefix + prompt, answer, choices))
    problems = [("A", "the location"), ("B", "the facilities in the club"), ("C", "the membership conditions")]
    add(qs, 17, ["Bridges Centre", "Shapes", "Jack's Gym", "Jetts Fitness"], "BCAB",
        "What is the problem with each of the following health clubs? Write the correct letter, A, B or C.",
        problems, "matching")
    comments = [(c, t) for c, t in zip("ABCDEFGH", [
        "very boring", "too difficult", "specialised equipment needed", "very expensive",
        "immediate results", "useful practice for maths", "cheap to do", "takes longer than usual to do"])]
    add(qs, 21, ["Steam engine", "Breakfast cereals", "Bouncing balls", "Making paper", "Tie-dyeing", "Glue from milk"],
        "BGFAHE", "What is said about each of the following experiments? Choose SIX answers from the box, A-H.",
        comments, "matching")
    letters = [(c, "") for c in "ABCDEFG"]
    add(qs, 27, ["Metal container", "Integral strainer", "Drip tip", "Pottery container"], "DFGC",
        "[Condenser] Label the diagram. Write the correct letter, A-G.", letters, "matching")
    add(qs, 31, [
        "the second type (Cumulus) resembling a cone-shaped ___",
        "The third type of cloud was compared to a flat ___",
        "criticism for the ___ used in naming clouds",
        "even composed ___ praising the beauty of clouds",
        "The ___ influenced British art",
        "increasing or decreasing rainfall or ___",
        "___ were sometimes employed to deliver man-made materials",
        "water pollution, as observed in a ___ in Australia",
        "some research focuses on using ___ as a safer alternative",
        "weather changes can significantly impact people's ___ abilities",
    ], ["tower", "sheet", "terminology", "poetry", "classification", "fog", "rockets", "lake", "salt", "memory"],
        "[Cloud Science] Complete the notes. Write ONE WORD ONLY for each answer.")
    return qs


def listening18_notes():
    return {
        "1": """<ul>
<li>Area of living: in the west of Perth</li>
<li>Best option – Minack Library</li>
<li>Located in [[1]] Street, next to the [[2]]</li>
<li>Saturdays: open until [[3]] p.m.</li>
</ul>
<p><strong>Children's activities</strong></p>
<ul><li>a [[4]] club (5–13 year olds)</li><li>a [[5]] club (every other Saturday)</li></ul>
<p><strong>Adult activities</strong></p>
<ul><li>Book of the Month club</li><li>Can meet local [[6]] (about once a year)</li></ul>
<p><strong>Services</strong></p>
<ul>
<li>Can borrow [[7]]</li>
<li>Computers are available (can be booked)</li>
<li>Various [[8]] are available</li>
<li>Can drop off books, etc. via the letter box (must give card [[9]])</li>
</ul>
<p><strong>Library shop sells</strong></p>
<ul><li>Postcards (small selection)</li><li>[[10]] (wide range)</li></ul>""",
        "31": """<p><strong>Origins</strong></p>
<ul>
<li>A British scientist classified clouds into three shapes, with the second type (Cumulus) resembling a cone-shaped [[31]]</li>
<li>The third type of cloud was compared to a flat [[32]]</li>
<li>The scientist faced criticism for the [[33]] used in naming clouds, as English was not his native language.</li>
<li>Despite the critiques, he gained fame as a scientific celebrity and even composed [[34]] praising the beauty of clouds.</li>
</ul>
<p><strong>Cultural and Artistic Impacts</strong></p>
<ul>
<li>The [[35]] influenced British art, inspiring artists to incorporate cloud depictions into their works.</li>
<li>Scientists experimented with altering weather conditions, such as increasing or decreasing rainfall or [[36]].</li>
<li>[[37]] were sometimes employed to deliver man-made materials for weather modification.</li>
</ul>
<p><strong>Modern Weather Science</strong></p>
<ul>
<li>The use of silver iodide in weather experiments led to water pollution, as observed in a [[38]] in Australia.</li>
<li>Today, some research focuses on using [[39]] as a safer alternative for weather manipulation.</li>
<li>Research into the psychological effects of weather shows that weather changes can significantly impact people's [[40]] abilities.</li>
</ul>""",
    }


# The scan has no text layer, so the passage is transcribed here.
BUSINESS_CARDS = """
The ritual may be universal, but the details of business cards and how they are swapped vary across countries. Americans throw their cards casually across a table; the Japanese make the exchange of cards a formal ceremony. While there are cards that are discreet and understated, others are crammed full of details and titles. Some businesspeople hand out 24-carat gold cards, and there are kindergarten children who have cards with not only their own contact details, but also with the job descriptions of their parents and even grandparents. This practice has become so common in parts of New York, for example, that the use of such cards is now prohibited by some of these institutions.

Cards have been around a long time in one form or another. The Chinese invented calling cards in the 15th century to give people notice that they intended to pay them a visit, but these were for social purposes only. Then, in the 17th century, European businesspeople invented a new type of card to act as miniature advertisements, signalling the advent of the business card. In today's world, business cards can cause people to have strong emotional reactions. According to one experienced company director, very few things can provoke more heated discussion at a board meeting than the composition of the company's business cards.

Lots of companies try to promote themselves by altering the form of the card. Employees at one famous toy company give out little plastic figures with their contact details stamped on them. One fast food company has business cards which are shaped like a portion of French fries. A Canadian divorce lawyer once gave out cards that could be torn in two – one half for each of the spouses. For many business commentators, such gimmicky business cards prove that the use of a physical business card is nearly at an end. After all, why bother exchanging bits of thick paper at all when you can simply swap electronic versions by smartphone.

However, one can just as well argue the opposite: that business cards are here to stay, and in a business world full of meetings and correspondence, it is more important than ever that your card is unique. Attempts to reinvent business cards for the digital age have not been successful. Even at the latest technology conferences, people still greet each other by handing out little rectangles made from paper rather than using a digital alternative.

To understand business cards, it is necessary to understand how business works. That business cards are thriving in a digital age is a forceful reminder that there is much about business that is timeless. According to Kate Jones, a business lecturer, there is one eternal and inescapable issue. Her 2006 study of more than 200 business executives in North America found that trust was the key element for running a successful business. It is vital to be able to look someone in the eye and decide what sort of person they are. In this way, you can transform acquaintanceships into relationships. A good proportion of business life will always be about building social connections – having dinner or playing sport with clients and colleagues – and while computers can deal with administrative tasks, it is still human beings that have to focus on the emotional.

The rapid advance of globalisation means that this relationship building process is becoming ever more demanding. Managers have to put more effort in when dealing with international counterparts, especially when there is not a common language, which is so often the case these days. A recent UK survey showed that chief executives of global organisations now routinely spend three out of every four weeks on international travel. It is in these situations that business cards are doubly useful, as they are a quick way of establishing connections. Cards can also remind you that you have actually met someone in a face to face meeting rather than just searched for them on the internet. Looking through piles of different cards can enhance your memory in ways that simply looking through uniform electronic lists would never do.

Janet McIntyre is a leading expert on business cards in today's world. She maintains that as companies become more complex, cards are essential in determining the exact status of every contact you meet in multinational corporations. Janet also explains how exchanging business cards can be an effective way of initiating a conversation, because it gives people a ritual to follow when they first meet a new business contact.

The business world is obsessed with the idea of creating and inventing new things that will change the way we do everything, and this does lead to progress. But there are lots of things that do not need to be changed and in Janet McIntyre's view, tradition also has an equally valuable role to play. Therefore the practice of exchanging business cards is likely to continue in the business world.
"""

# The scan has no text layer, so the passage is transcribed here.
SLOWNESS = """
A The English explorer and writer John Franklin (1786-1847) joined the Navy at the age of 14, and fought at the battle of Trafalgar. When peace came, he turned his attention to Arctic exploration, and in particular to solving the conundrum of the Northwest Passage, a mythical clear-water route through the ice which would, if it existed, link the Pacific Ocean on America's West Coast with the Atlantic on its East. The first expedition Franklin led to the Arctic was an arduous overland journey lasting from 1819 to 1822, in which he and his twenty-strong team covered 8880 kilometres on foot. Their expedition was a triumph of surveying – they managed to chart hundreds of kilometres of previously unknown coastline – but food ran out on their journey back to civilisation, and the men were forced to eat their belts and their boots (which they boiled up to make leather soup).

B There followed a career as a travel writer and public speaker ('the man who ate his boots' was Franklin's tag-line). Then in 1845, Franklin set off back to the Arctic with two ships – the Erebus and the Terror – and 129 men. Nothing was heard of them for 14 years, although more than 30 expeditions were dispatched in search of them. Eventually it was discovered that Franklin and all his team had perished after their ships were trapped in the ice.

C In his personal correspondence and published memoirs, Franklin comes across as a man dedicated to the external duties of war and exploration, who kept introspection and self-analysis to a minimum. His blandness makes him an amenably malleable subject for a novelist, and Sten Nadolny has taken full advantage of this in his book. Most important, Nadolny has endowed John Franklin with a defining trait for which there is no historical evidence: Langsamkeit ('slowness', or 'calmness').

D Slowness influences not only Franklin's behaviour, but also his vision, his thought and his speech. The opening scene of The Discovery of Slowness depicts Franklin as a young boy, failing to catch a ball because his reaction time is too slow. Despite the bullying of his peers, Franklin resolves not to fall into step with 'their way of doing things'. For Nadolny, Franklin's fascination with the Arctic stems from his desire to find an environment suited to his peculiar slowness. He describes Franklin as a boy dreaming of the 'time without hours and days' which exists in the far north, a place 'where nobody would find him too slow'.

E Ice is a slow mover. The compressed blue ice inside an Alpine crevasse will have fallen as snow several decades earlier. Polar pack ice takes at least two years to form. The film of crystals which first appears on the surface of the sea thickens into a silkily pliant layer called nilas; this in turn consolidates into young ice, which then deepens during several seasons to become pack. Ice demands a corresponding patience from those who venture onto it. The explorers who have thrived at high latitudes and at high altitudes haven't usually been men of great speed. They have tended instead to demonstrate unusual self-possession, a considerable capacity for boredom, and a talent for the uncomplaining endurance of suffering.

F These were all qualities which the historical Franklin possessed in abundance, and so Nadolny's exaggeration of them isn't unreasonable. Even as an adult, Franklin's slowness of thought means that he is unable to speak fluently, so he learns by heart 'entire fleets of words and batteries of responses', and speaks a languid, bric-a-brac language. In the Navy, his method of thinking first and acting later initially provokes mockery from his fellow sailors. But Franklin persists in doing things his way, and gradually earns the respect of those around him. To a commodore who tells him to speed up his report of an engagement, he replies: 'When I tell something, sir, I use my own rhythm.' A lieutenant says approvingly of him: 'Because Franklin is so slow, he never loses time.'

G Nadolny also brings his central metaphor of slowness to bear on the novel's language. The chapters describing Franklin's early years are a medley of separate fragments, rhetorical questions, associative jumps and exclamation marks. In the later sections recounting Franklin's first Arctic expedition, Nadolny brilliantly sets the narrative pace to the rhythms of the frozen landscape, and to the 'slowness which is bred by hunger'.

H Since it was first published in Germany in 1983, The Discovery of Slowness has sold more than a million copies and been translated into 15 languages. It has been adopted as a manual and manifesto by European pressure groups and institutions representing causes as diverse as sustainable development, management science and motoring policy, even becoming involved in the debate about speed limits on German roads. The various groups that have taken the novel up have one thing in common: a dislike of the high-speed culture of Postmodernity. Nadolny's Franklin appeals to them because he is immune to 'the compulsion to be constantly occupied', and to the idea that 'someone was better if he could do the same thing fast'. It's easy to see where the attraction lies for those in management. The novel is crammed with quotations about time-efficiency, punctiliousness and profitability: 'What did too late mean? They hadn't waited for it long enough, that's what it meant.'
"""


def reading18_content():
    nano = pdf_text("Passage 2 Nanotechnology.pdf")
    nano = between(nano, "Nanotechnology: the science of the very small", "Questions 14")
    return (
        plain_passage("The Importance of Business Cards", BUSINESS_CARDS,
                      "The exchanging of business cards is as close to a universal ritual as you can find in the business world")
        + lettered_passage("Nanotechnology: the science of the very small", nano, "A-H")
        + lettered_passage("Book Review: The Discovery of Slowness", SLOWNESS, "A-H",
                           "The Discovery of Slowness by Sten Nadolny, translated by Ralph Freedman | Canongate, 311 pp")
    )


def reading18():
    qs = []
    add(qs, 1, [
        "Children's business cards have been banned in some kindergartens.",
        "It was the Chinese who first began the practice of using business cards.",
        "Designing business cards can be a controversial process for some companies.",
        "A famous toy company has boosted their sales by using one type of unusual business card.",
        "Some business commentators predict a decline in the use of paper business cards.",
    ], ["TRUE", "FALSE", "TRUE", "NOT GIVEN", "TRUE"],
        "[The Importance of Business Cards] Do the following statements agree with the information given in Reading Passage 1? Write TRUE, FALSE or NOT GIVEN.",
        TFNG)
    add(qs, 6, [
        "The most important aspect of business is having ___ in others.",
        "___ do not have the ability to establish the good relationships essential to business.",
        "Managers must work harder when they don't share the same ___ with their contacts.",
        "A UK survey indicates that ___ takes up the largest part of business leaders' time.",
        "A business person's ___ of a meeting can be improved by looking at business cards.",
        "Business cards clearly show the ___ of each person in a large company.",
        "The ritual of swapping business cards is a good way of starting a ___ at the beginning of a business relationship.",
        "Janet feels that in the business world, ___ is just as important as innovation.",
    ], ["trust", "computers", "language", "travel", "memory", "status", "conversation", "tradition"],
        "[How business works] Complete the notes below. Choose ONE WORD ONLY from the passage for each answer.")

    add(qs, 14, [
        "In the same way that a child may use ___ scientists are now able to create new structures",
        "comparing the exact ___ of one atom with that of a single human hair",
        "a long-lasting ___ widely available today, relies on minute nanoparticles",
    ], ["bricks", "diameter", "sunscreen"],
        "[Nanotechnology] Complete the summary. Write ONE WORD ONLY from the text for each answer.")
    paragraphs = [(c, f"Paragraph {c}") for c in "ABCDEFGH"]
    add(qs, 17, [
        "a comparison between two of the world's vital natural resources",
        "a mention of how nanotechnology could be dangerous for humans",
        "a claim that nanotechnology has influenced modern authors",
        "a reference to the fact that nanotechnology has achieved more than was anticipated a decade ago",
        "a suggestion that nanotechnology could provide financial as well as ecological benefits",
        "an acknowledgement that more time is required to realise some of nanotechnology's potential",
    ], "EFAGHD", "The text has eight paragraphs, A–H. Which paragraph contains the following information?",
        paragraphs, "matching")
    choose_two(qs, 23, "Choose TWO letters, A-E.\nWhich TWO of the following statements does the writer make about nanotechnology and energy resources?", "C/D", [
        ("A", "Nanotechnology means that solar energy will replace fossil fuel energy."),
        ("B", "We have made solar batteries for the first time by applying nanotechnology."),
        ("C", "Further research is needed to turn nanotechnology into practical energy solutions."),
        ("D", "Nanotechnology is being used to remove dangerous gases from the atmosphere."),
        ("E", "Nanotechnology has helped create cheaper sources of energy."),
    ])
    choose_two(qs, 25, "Choose TWO letters, A-E.\nIn which TWO ways does the writer think nanotechnology could improve food production?", "B/D", [
        ("A", "by enabling crops to grow faster"), ("B", "by keeping food fresh for longer"),
        ("C", "by making food tastier"), ("D", "by protecting food from insects better"),
        ("E", "by increasing the variety of food"),
    ])

    add(qs, 27, [
        "a summary of Franklin's occupation in the period before his first expedition",
        "a reference to a feature of Franklin's character in Nadolny's novel that has no definite basis in fact",
        "a connection between the central theme of the novel and an environmental process",
        "a reference to the widespread appeal of Nadolny's novel",
        "a summary of events following Franklin's return from his first expedition",
    ], "ACEHB", "[Book Review: The Discovery of Slowness] Reading Passage 3 has eight paragraphs, A-H. Which paragraph contains the following information?",
        paragraphs, "matching")
    words = [(c, w) for c, w in zip("ABCDEFGHIJKL", [
        "a bully", "discoveries", "educational", "family", "isolation", "an outsider",
        "personality", "problems", "remoteness", "a scholar", "sporting", "timelessness"])]
    add(qs, 32, [
        "Little is known from Franklin's correspondence and published writings about his ...",
        "He begins the book by showing how this affects the young Franklin's ... activities,",
        "and makes him become ...",
        "As a child, it is the quality of ... that attracts Franklin to the Arctic.",
    ], "GKFL", "[John Franklin and the Quality of Slowness] Complete the summary using the list of words, A-L.",
        words, "matching")
    mcqs = [
        ("In paragraph E, the writer describes different types of ice in order to illustrate", "D", [
            ("A", "the extreme conditions that Polar explorers have to face."), ("B", "the unusual quality of the beauty of Polar regions."),
            ("C", "the vital importance of preserving the Arctic environment."), ("D", "the personal qualities required of an explorer in Arctic conditions.")]),
        ("What is said about the way Franklin communicates?", "C", [
            ("A", "He expresses a very limited range of ideas."), ("B", "He is only willing to discuss things he is familiar with."),
            ("C", "He uses words and phrases that he has previously memorised."), ("D", "He is only fluent when talking about naval matters.")]),
        ("How does the attitude of the other sailors change towards Franklin?", "D", [
            ("A", "They no longer notice his slowness."), ("B", "They start to copy his approach to work."),
            ("C", "They begin to recognise his efforts to overcome his problems."), ("D", "They eventually appreciate his good qualities.")]),
        ("The chapters of The Discovery of Slowness which describe Franklin's early years contain", "B", [
            ("A", "text from a wide variety of sources."), ("B", "short, disconnected pieces of text."),
            ("C", "descriptions of the Arctic landscape."), ("D", "information about other explorers like Franklin.")]),
        ("The Discovery of Slowness has achieved widespread popularity because", "A", [
            ("A", "it reflects many people's concern about one aspect of modern life."), ("B", "it offers achievable solutions to many of the problems of today."),
            ("C", "it tells the story of someone's triumph over personal problems."), ("D", "it shows how life in the past was less pressured than it is now.")]),
    ]
    for offset, (prompt, answer, choices) in enumerate(mcqs):
        prefix = "Choose the correct letter, A, B, C or D.\n" if offset == 0 else ""
        qs.append(question(36 + offset, prefix + prompt, answer, choices))
    return qs


def reading18_notes():
    return {
        "6": """<p><strong>Kate Jones's research</strong></p>
<ul><li>The most important aspect of business is having [[6]] in others.</li>
<li>[[7]] do not have the ability to establish the good relationships essential to business.</li></ul>
<p><strong>Business and globalisation</strong></p>
<ul><li>Managers must work harder when they don't share the same [[8]] with their contacts.</li>
<li>A UK survey indicates that [[9]] takes up the largest part of business leaders' time.</li>
<li>A business person's [[10]] of a meeting can be improved by looking at business cards.</li></ul>
<p><strong>Janet McIntyre</strong></p>
<ul><li>Business cards clearly show the [[11]] of each person in a large company.</li>
<li>The ritual of swapping business cards is a good way of starting a [[12]] at the beginning of a business relationship.</li>
<li>Janet feels that in the business world, [[13]] is just as important as innovation.</li></ul>""",
        "14": """<p>In the same way that a child may use [[14]], scientists are now able to create new structures by combining the smallest particles known to man. We can fully appreciate the microscopic scale of this work by comparing the exact [[15]] of one atom with that of a single human hair.</p>
<p>A lot of today's electronic consumer goods, such as lasers, have components that are microscopic in size. They are not the only products relying on nanotechnology. For example, a long-lasting [[16]], widely available today, relies on minute nanoparticles for its effectiveness. This was developed in the 1990s as a result of concerns about the safety of existing products.</p>""",
        "32": """<p>Little is known from Franklin's correspondence and published writings about his [[32]]. The author, Nadolny, suggests that Franklin's whole life can be explained by the quality of 'slowness'. He begins the book by showing how this affects the young Franklin's [[33]] activities, and makes him become [[34]]. As a child, it is the quality of [[35]] that attracts Franklin to the Arctic.</p>
<div class="summary-word-bank">
<span><strong>A</strong> a bully</span><span><strong>B</strong> discoveries</span><span><strong>C</strong> educational</span><span><strong>D</strong> family</span>
<span><strong>E</strong> isolation</span><span><strong>F</strong> an outsider</span><span><strong>G</strong> personality</span><span><strong>H</strong> problems</span>
<span><strong>I</strong> remoteness</span><span><strong>J</strong> a scholar</span><span><strong>K</strong> sporting</span><span><strong>L</strong> timelessness</span>
</div>""",
    }


# --------------------------------------------------------------------------

def make_exam(number, audio, listening, listening_notes, content, reading, reading_notes,
              task1_image, task1, task2, question_images=None):
    listen = {
        "title": "Listening", "section_type": "listening", "order": 1, "duration_minutes": 40,
        "audio_file": f"../../TESTLAR/13/{audio}", "notes": listening_notes, "content": "",
        "questions": listening,
    }
    if question_images:
        listen["question_images"] = question_images
    return {
        "title": f"IELTS Full Mock Test {number}",
        "description": "To‘liq IELTS Academic mock test: Listening, Reading va Writing.",
        "exam_type": "mock", "price": 0, "duration_minutes": 170, "is_active": True,
        "sections": [
            listen,
            {"title": "Reading", "section_type": "reading", "order": 2, "duration_minutes": 60,
             "notes": reading_notes, "content": content, "questions": reading},
            {"title": "Writing", "section_type": "writing", "order": 3, "duration_minutes": 60,
             "image": f"images/{task1_image}", "content": "", "questions": [
                 question(1, task1, "", kind="writing_task", word_limit=150),
                 question(2, task2, "", kind="writing_task", word_limit=250),
             ]},
        ],
    }


def main():
    from PIL import Image

    IMAGES.mkdir(parents=True, exist_ok=True)
    # Keep only the charts: the first photo has a clipped "IELTS Bar Chart"
    # header, the second repeats the whole task text the question shows.
    Image.open(SOURCE / "photo_2026-11-28_08-46-50.jpg").crop((0, 26, 576, 337)).save(
        IMAGES / "mock_test_17_task1.jpg", quality=95)
    Image.open(SOURCE / "photo_2026-11-28_08-46-55.jpg").crop((0, 216, 512, 491)).save(
        IMAGES / "mock_test_18_task1.jpg", quality=95)
    # The condenser diagram (Listening Q27-30) is on page 5 of the TEST 6
    # booklet; crop away the instructions and the answer lines below it.
    rendered = IMAGES / "mock_test_18_condenser_page.jpg"
    subprocess.run(["pdftoppm", "-f", "5", "-singlefile", "-jpeg", "-r", "170",
                    str(SOURCE / "TEST 6 (JF).pdf"), str(rendered.with_suffix(""))], check=True)
    Image.open(rendered).crop((165, 330, 1270, 1085)).save(IMAGES / "mock_test_18_condenser.jpg", quality=92)
    rendered.unlink()

    exam17 = make_exam(
        17, "listening17.mp3", listening17(), listening17_notes(),
        reading17_content(), reading17(), reading17_notes(), "mock_test_17_task1.jpg",
        "The chart below shows the expenditure of two countries on consumer goods in 2010. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
        "Cash is being replaced by card and mobile payments in many countries. Is this a positive or negative development?",
    )
    exam18 = make_exam(
        18, "listening18.mp3", listening18(), listening18_notes(),
        reading18_content(), reading18(), reading18_notes(), "mock_test_18_task1.jpg",
        "The bar chart shows the number of hours men and women spent on different tasks on average per day in 2011. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
        "Some people think fast food is harming public health. What are the causes of its popularity? What can governments do to encourage healthier eating?",
        {"27": "images/mock_test_18_condenser.jpg"},
    )
    for number, exam in [(17, exam17), (18, exam18)]:
        (DATA / f"ielts_full_mock_test_{number}.json").write_text(
            json.dumps(exam, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
