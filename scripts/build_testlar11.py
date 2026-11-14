#!/usr/bin/env python3
"""Build the two database-backed mock exams supplied in TESTLAR/11."""
from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TESTLAR" / "11"
DATA = ROOT / "data" / "cambridge"
IMAGES = DATA / "images"


def pdf_text(name: str) -> str:
    return subprocess.check_output(
        ["pdftotext", "-layout", str(SOURCE / name), "-"], text=True
    ).replace("\f", "\n")


def passage_html(name: str, marker: str) -> str:
    raw = pdf_text(name).split(marker, 1)[0]
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"\d+", line):
            continue
        if line.startswith(("READING PASSAGE", "You should spend", "Read the text", "Part 2", "Part 3")):
            continue
        lines.append(line)
    text = " ".join(lines)
    text = re.sub(r"(?<=\w)- (?=\w)", "", text)
    title = Path(name).stem.replace("Passage 1 ", "").replace("Passage 2 ", "").replace("Passage 3 ", "")
    return f"<h2>{html.escape(title)}</h2><p>{html.escape(text)}</p>"


def opts(items):
    return [{"key": str(k), "text": v} for k, v in items]


def q(order, text, answer, choices=None, kind=None):
    return {
        "order": order,
        "text": text,
        "question_type": kind or ("mcq" if choices else "gap_fill"),
        "correct_answer": str(answer),
        "options": opts(choices or []),
        "explanation": "",
        "word_limit": 0,
        "model_answer": "",
    }


ABC = lambda a, b, c: [("A", a), ("B", b), ("C", c)]


def listening_notes(number):
    if number == 14:
        return {
            "1": """<h5>Amateur Dramatic Society</h5>
<p><strong>Secretary:</strong> Jane Caulfield</p>
<p><strong>Mailing address:</strong> 117 Green Road, Prestwin</p>
<p><strong>Location for rehearsals:</strong> The [[1]] House, Wynn</p>
<p>No experience necessary</p>
<p>They need actors and [[2]] singers</p>
<p>Also need people who can [[3]]</p>
<p>Meetings 6–8 p.m. every [[4]]</p>
<p>Closed in [[5]] (for 2 weeks)</p>
<h5>Membership costs</h5>
<p><strong>Standard:</strong> £40 (includes a [[6]] once a year)</p>
<p><strong>Over 60s or unemployed:</strong> £[[7]]</p>
<p><strong>Youth group:</strong> for people aged [[8]] years old and under</p>
<h5>Shows</h5>
<p>mostly plays by [[9]] authors</p>
<p>family show in December (raises money for children’s [[10]])</p>""",
            "31": """<h5>Crisis Communication Theory</h5>
<p>Some people think using [[31]] is better than theory, but a lot of advice is simply a [[32]].</p>
<p>The organisation can be a victim, e.g. due to a [[33]]. A preventable crisis results from a [[34]] in the organisation.</p>
<p>Communicate what [[35]] is to be taken and provide [[36]] that the crisis is not so bad.</p>
<p>The initial objective is to lessen [[37]] opinions. Rebuild strategies matter when there is a serious [[38]] to reputation.</p>
<p>Things can be improved by providing an [[39]]. In serious cases, [[40]] is usually offered.</p>""",
        }
    return {
        "1": """<h5>Film Club</h5>
<h5>Membership information</h5>
<p>Club meets every 2 weeks</p>
<p>No [[1]] limit</p>
<p>Student membership costs £[[2]] per season</p>
<p>Members get free entry to club films and £[[3]] reduction on other films.</p>
<p>Members are entitled to 3 hours’ free [[4]].</p>
<h5>Films to be shown</h5>
<p><strong>Oct 14 — Pablo:</strong> about a child in [[5]] who runs away and wins a [[6]] competition on TV.</p>
<p><strong>Oct 28 — The Soldier:</strong> with live [[7]] accompaniment; made in [[8]]; type of film: a [[9]].</p>
<p><strong>Nov 11 — Tiger:</strong> followed by a [[10]] by the director.</p>""",
        "31": """<h5>Office Design</h5>
<p><strong>Early 20th Century:</strong> workers employed to do [[31]] were arranged in rows.</p>
<p>First, workers had individual [[32]]; later, cubicles with high or low [[33]]; nowadays workers may have to [[34]] a work area.</p>
<p>Employees report a lack of [[35]] and [[36]], and a risk to their [[37]].</p>
<p>Employers say open plans reduce rent and [[38]] costs and make [[39]] staff easier.</p>
<p>In reality, employees are often distracted by the [[40]] in the office.</p>""",
    }


def reading_notes(number):
    if number != 15:
        return {}
    return {
        "18": """<h5>The wooden block task</h5>
<p>Children were given a task involving blocks of wood. The blocks varied according to how their weight was distributed: the weight distribution was [[18]] in some but not in others. This was because the others were either tapered or had had [[19]] inserted in them. In the latter case, the differences between the blocks were [[20]].</p>
<p>The children were instructed to balance each block on a [[21]]. Some children, usually the youngest ones, did the task by dealing with each block [[22]]. In other cases, children quickly started to look for [[23]]. For example, they initially presumed that all the blocks balanced in the middle. They then had to revise their ideas.</p>
<div class="summary-word-bank">
<span><strong>A</strong> invisible</span><span><strong>B</strong> ways</span><span><strong>C</strong> others</span><span><strong>D</strong> wood</span>
<span><strong>E</strong> individually</span><span><strong>F</strong> repeatedly</span><span><strong>G</strong> symmetrical</span><span><strong>H</strong> rules</span>
<span><strong>I</strong> weight</span><span><strong>J</strong> beam</span><span><strong>K</strong> metal</span>
</div>"""
    }


def listening14():
    questions = []
    gaps = [
        "Location for rehearsals: The ___ House, Wynn",
        "They need actors and ___ singers", "Also need people who can ___",
        "Meetings 6–8 p.m. every ___", "Closed in ___ (for 2 weeks)",
        "Standard membership: £40 (includes a ___ once a year)",
        "Over 60s or unemployed: £___", "Youth group: for people aged ___ years old and under",
        "Shows: mostly plays by ___ authors", "Family show raises money for children’s ___",
    ]
    answers = ["club", "male", "drive", "Tuesday", "August", "dinner", "25", "16/sixteen", "modern", "hospital"]
    for i, (text, answer) in enumerate(zip(gaps, answers), 1):
        questions.append(q(i, ("[Amateur Dramatic Society] Complete the notes. Write ONE WORD AND/OR A NUMBER.\n" if i == 1 else "") + text, answer))
    part2 = [
        ("The speaker stresses the importance to Clifton Bird Park of", "A", ABC("birds that are now endangered", "birds from all over the world", "birds that are common in the local area")),
        ("People who volunteer to help with gardening at the park", "B", ABC("must work at weekends", "need to come at least once a month", "will only be required in the busy season")),
        ("Who would be the ideal gardening volunteer?", "B", ABC("someone who can work independently", "someone willing to work in any weather", "someone who knows a lot about plants")),
        ("Volunteer guides will mainly be working with", "A", ABC("international visitors", "local people from Clifton", "school groups")),
        ("What is still required for the Maintenance Day?", "B", ABC("food and drink", "transport", "tools")),
    ]
    for i, (text, ans, choices) in enumerate(part2, 11):
        questions.append(q(i, ("[Information for Volunteers at Clifton Bird Park] Choose A, B or C.\n" if i == 11 else "") + text, ans, choices))
    # Empty option labels make the renderer use one compact A–H grid instead
    # of repeating eight long "Location A" cards below every map question.
    map_choices = [(c, "") for c in "ABCDEFGH"]
    for i, (name, ans) in enumerate(zip(["Wooden bridge", "Observation tower", "Visitor cabins", "Nesting boxes", "Boat sheds"], "FHCEB"), 16):
        questions.append(q(i, ("[Clifton Bird Park map] Label the map.\n" if i == 16 else "") + name, ans, map_choices, kind="matching"))
    part3 = [
        ("Why mention the Mountain Code?", "A", ABC("It is the most relevant to their field trip", "It also applies to caves", "It covers the whole country")),
        ("Why do some participants harm the environment?", "C", ABC("They fail to recognise rare plants", "They do not realise how fragile it is", "They get too absorbed in their tasks")),
        ("Which rule about taking samples is most important?", "C", ABC("Leave the area in its natural state", "Avoid removing fossils", "Keep collecting to a minimum")),
        ("Which aspect of taking samples must they still find out about?", "A", ABC("taking them from private land", "taking them from rock faces", "taking them from man-made structures")),
        ("What coastal danger will they emphasise?", "B", ABC("falling rock", "tidal movements", "unstable sand")),
    ]
    for i, (text, ans, choices) in enumerate(part3, 21):
        questions.append(q(i, ("[Geology field trip to Iceland] Choose A, B or C.\n" if i == 21 else "") + text, ans, choices))
    topics = opts([(c, t) for c, t in zip("ABCDEFG", ["unique geological features of Iceland", "replacement of fossil fuels", "negative changes due to human activity", "energy for agriculture", "health risks of eruptions", "risk of flooding", "long-term effects of volcanoes"])])
    for i, (name, ans) in enumerate(zip(["Geothermal Fields", "The Hot Spot", "Glaciers", "Basalt Rock", "Geothermal Power Plants"], "DAFGB"), 26):
        questions.append(q(i, ("Match each reading pack to its topic.\n" if i == 26 else "") + name, ans, [(x["key"], x["text"]) for x in topics], kind="matching"))
    final_texts = ["using ___ is better than theory", "a lot of advice is simply a ___", "a victim crisis may be due to a ___", "a preventable crisis results from a ___ in the organisation", "communicate what ___ is to be taken", "provide ___ that the crisis is not so bad", "lessen ___ opinions", "a serious ___ to reputation", "providing an ___", "in serious cases, ___ is offered"]
    final_answers = ["logic", "guess", "rumour/rumor", "mistake", "action", "proof", "negative", "threat", "apology", "compensation"]
    for i, (text, ans) in enumerate(zip(final_texts, final_answers), 31):
        questions.append(q(i, ("[Crisis Communication Theory] Complete the notes. Write ONE WORD ONLY.\n" if i == 31 else "") + text, ans))
    return questions


def listening15():
    questions = []
    texts = ["No ___ limit", "Student membership costs £___ per season", "£___ reduction on other films", "three hours’ free ___", "Pablo is about a child in ___", "wins a ___ competition", "live ___ accompaniment", "made in ___", "type of film: a ___", "followed by a ___ by the director"]
    answers = ["age", "21.50", "2", "parking", "Argentina", "singing", "piano", "1922", "comedy", "talk"]
    for i, (text, ans) in enumerate(zip(texts, answers), 1):
        questions.append(q(i, ("[Film Club] Write ONE WORD AND/OR A NUMBER.\n" if i == 1 else "") + text, ans))
    p2 = [
        ("Why did the founders originally need help?", "A", ABC("preparing fields for planting", "harvesting organic crops", "constructing farm buildings")),
        ("To remain an active member you must", "A", ABC("update your form every year", "pay $25 every year", "use the scheme every year")),
        ("Most volunteers search for jobs according to", "B", ABC("type of work", "geographical location", "length of time")),
        ("The host and volunteer should", "A", ABC("confirm details in writing", "draw up a formal contract", "meet before setting terms")),
        ("How are members’ problems dealt with?", "B", ABC("checking each new member", "allowing online feedback", "inspecting work and accommodation")),
    ]
    for i, (text, ans, choices) in enumerate(p2, 11):
        questions.append(q(i, ("[extrahands.com] Choose A, B or C.\n" if i == 11 else "") + text, ans, choices))
    jobs = [(c, t) for c, t in zip("ABCDEFG", ["cook", "gardener", "construction worker", "tour guide", "farm labourer", "editor", "swimming pool cleaner"])]
    for i, (country, ans) in enumerate(zip(["Portugal", "Australia", "South Korea", "USA", "Italy"], "FADBC"), 16):
        questions.append(q(i, ("Which job did Stephen do in this country?\n" if i == 16 else "") + country, ans, jobs, kind="matching"))
    p3 = [
        ("What problem is Lorna having with her report?", "B", ABC("listing the references", "keeping to the word limit", "writing the evaluation")),
        ("Why did Charles take the course?", "C", ABC("improve job prospects", "increase self-confidence", "develop self-expression")),
        ("Which work did Lorna most enjoy?", "C", ABC("individual work", "pair work", "group work")),
        ("Which course content interested both students?", "A", ABC("song structure", "writing a chorus", "lyrical styles and forms")),
        ("Lorna found writing a song", "B", ABC("impossible", "tiring", "amusing")),
    ]
    for i, (text, ans, choices) in enumerate(p3, 21):
        questions.append(q(i, ("[Song-writing course for drama students] Choose A, B or C.\n" if i == 21 else "") + text, ans, choices))
    focus = [(c, t) for c, t in zip("ABCDEFGH", ["use of own memories", "full use of the stage", "relaxation techniques", "physical expression of character", "play readings", "acting without preparation", "using a range of accents", "following instructions"])]
    for i, (teacher, ans) in enumerate(zip(["Bob Lacey", "Evelyn Chance", "Ted Winter", "Kevin Gray", "Dorothy Thomas"], "GBDHC"), 26):
        questions.append(q(i, ("Match each teacher to the workshop focus.\n" if i == 26 else "") + teacher, ans, focus, kind="matching"))
    final = ["workers employed to do ___ were arranged in rows", "workers had individual ___", "cubicles with high or low ___", "workers may have to ___ a work area", "lack of ___", "lack of ___", "risk to our ___", "reduce rent and ___ costs", "make ___ staff easier", "distracted by the ___ in the office"]
    final_answers = ["typing", "desks", "screens", "share", "privacy", "security", "health", "energy", "training", "noise"]
    for i, (text, ans) in enumerate(zip(final, final_answers), 31):
        questions.append(q(i, ("[Office Design] Complete the notes. Write ONE WORD ONLY.\n" if i == 31 else "") + text, ans))
    return questions


def reading14():
    qs = []
    answers = ["FALSE", "NOT GIVEN", "FALSE", "TRUE", "TRUE", "FALSE"]
    statements = ["All baobab species on Madagascar are unique to the island", "Adanson and Grandidier were the first foreign botanists to visit Madagascar", "The baobab can be found in most areas of Madagascar", "The Avenue des Baobabs landscape resulted from agricultural development", "The baobab provides useful products for local people", "There is general agreement about why baobabs fall down"]
    tf = [(x, x.title()) for x in ["TRUE", "FALSE", "NOT GIVEN"]]
    for i, (text, ans) in enumerate(zip(statements, answers), 1): qs.append(q(i, ("[The Baobabs of Madagascar] TRUE, FALSE or NOT GIVEN.\n" if i == 1 else "") + text, ans, tf))
    for i, (text, ans) in enumerate(zip(["water from nearby fields", "lone trees are at risk from", "space for ___ activity", "practice of ___ makes germination difficult", "disappearance of certain ___ which dispersed seeds", "making ___ of undamaged forest", "producing a ___ about local culture"], ["irrigation", "cyclones", "farming", "logging", "animals", "maps", "book"]), 7): qs.append(q(i, text, ans))
    headings = [(r, t) for r, t in zip(["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"], ["allows consumers to use more product", "many reasons for changes", "includes utensils", "consumed with contents", "compact packaging", "history of packaging", "indicates spoilage", "reusable packaging", "communicates ideas and attracts customers", "vanishes or decomposes quickly"])]
    for i, ans in enumerate(["ix", "ii", "iv", "i", "vii", "x", "v"], 14): qs.append(q(i, ("[The Future of Food Packaging] Match the paragraph to a heading.\n" if i == 14 else "") + f"Paragraph {chr(65+i-14)}", ans, headings, kind="matching"))
    dev = [(c, t) for c, t in zip("ABCDEF", ["expands under certain conditions", "vanishes in hot water", "nonstick material", "made from a vegetable product", "sweet hot-drink container", "round edible container"])]
    for i, (company, ans) in enumerate(zip(["KFC", "Loliware", "Tomorrow Machine"], "EDA"), 21): qs.append(q(i, company, ans, dev, kind="matching"))
    for i, (text, ans) in enumerate(zip(["In Japan, ___ has been edible packaging for years", "Liquiglide helps bottles containing various ___", "Tomorrow Machine plans solid ___ as an oil container"], ["paper", "sauces", "sugar"]), 24): qs.append(q(i, text, ans))
    yn = [(x, x.title()) for x in ["YES", "NO", "NOT GIVEN"]]
    marine = ["Sponge hunting may have begun with one female dolphin", "Dolphin tool use may illuminate human tool origins", "Researchers generally agree on the link between tool use and intelligence", "Other scientists have criticised Dr Mann’s analysis"]
    for i, (text, ans) in enumerate(zip(marine, ["YES", "YES", "NO", "NOT GIVEN"]), 27): qs.append(q(i, ("[Marine Mammals Exhibit Ingenuity] YES, NO or NOT GIVEN.\n" if i == 27 else "") + text, ans, yn))
    mc = [
        ("Dolphins use sponges", "B", [("A", "to attract fish"), ("B", "to avoid injury"), ("C", "to supplement diet"), ("D", "as decoration")]),
        ("Sponge use results in dolphins", "C", [("A", "living longer"), ("B", "attracting mates"), ("C", "becoming isolated"), ("D", "becoming aggressive")]),
        ("The fisherman", "D", [("A", "explained the habit"), ("B", "made many observations"), ("C", "notified media"), ("D", "thought the sponge was a growth")]),
        ("Finding a sponge can take time because", "C", [("A", "some are heavy"), ("B", "they are rare"), ("C", "it must fit well"), ("D", "dolphins have individual preferences")]),
        ("Few sponge users allowed researchers to", "A", [("A", "compare behaviours within one species"), ("B", "track individuals"), ("C", "decide whether it was tool use"), ("D", "explain its purpose")]),
    ]
    for i, (text, ans, choices) in enumerate(mc, 31): qs.append(q(i, text, ans, choices))
    endings = [(c, t) for c, t in zip("ABCDEFGH", ["more frequent among females", "linked to a physical characteristic", "only possible in salt water", "more typical of males", "evidence of sound use", "threat to fishing", "learned by observing mothers", "not accepted by investigators"])]
    for i, (text, ans) in enumerate(zip(["A genetic explanation", "Observation of mothers", "Continued sponge use in adulthood", "Hunting in groups", "The dolphins’ clever behaviour"], "HGA DB".replace(" ", "")), 36): qs.append(q(i, text, ans, endings, kind="matching"))
    return qs


def reading15():
    qs = []
    tf = [(x, x.title()) for x in ["TRUE", "FALSE", "NOT GIVEN"]]
    st = ["Utzon was famous before designing the Opera House", "All four judges favoured the design from the beginning", "His knowledge of boats inspired parts of the design", "He was impressed by Mexican opera houses", "He changed designs after construction began", "Seidler defended Utzon’s role", "Utzon returned for the 1973 opening"]
    for i, (text, ans) in enumerate(zip(st, ["FALSE", "FALSE", "TRUE", "NOT GIVEN", "TRUE", "TRUE", "FALSE"]), 1): qs.append(q(i, ("[Sydney Opera House] TRUE, FALSE or NOT GIVEN.\n" if i == 1 else "") + text, ans, tf))
    for i, (text, ans) in enumerate(zip(["Final cost: $___", "Tiles came from ___", "Australian ___ covers outside walls", "___ resident companies", "large ___ below the staircase", "opening made the ___ visible"], ["102 million", "Sweden", "granite", "four/4", "forecourt", "harbour"]), 8): qs.append(q(i, text, ans))
    yn = [(x, x.title()) for x in ["YES", "NO", "NOT GIVEN"]]
    role = ["The teacher’s most important function is to develop good learning habits", "Success increased with age", "Children performed without teacher guidance", "Children frequently explained their rules clearly"]
    for i, (text, ans) in enumerate(zip(role, ["NOT GIVEN", "NO", "YES", "NO"]), 14): qs.append(q(i, ("[The Role of Errors in Learning] YES, NO or NOT GIVEN.\n" if i == 14 else "") + text, ans, yn))
    words = [(c, t) for c, t in zip("ABCDEFGHIJK", ["invisible", "ways", "others", "wood", "individually", "repeatedly", "symmetrical", "rules", "weight", "beam", "metal"])]
    for i, (text, ans) in enumerate(zip(["weight distribution was ___", "___ was inserted", "differences were ___", "balanced on a ___", "dealt with each block ___", "looked for ___"], "GKAJEH"), 18): qs.append(q(i, text, ans, words, kind="matching"))
    for i, (text, ans) in enumerate(zip(["a ___ problem", "by ___ him", "people dislike feeling ___"], ["geometry", "questioning", "ignorant"]), 24): qs.append(q(i, text, ans))
    pars = [(c, f"Paragraph {c}") for c in "ABCDEF"]
    for i, (text, ans) in enumerate(zip(["emotional satisfaction", "why beginners struggle", "error detection alongside mirroring", "human and primate mirror neurons compared", "integrating visual and motor processes", "first discovery of mirror neurons"], "DBECFB"), 27): qs.append(q(i, ("[How Does Watching Sport Influence the Brain?] Match information to a paragraph.\n" if i == 27 else "") + text, ans, pars, kind="matching"))
    implications = [(c, t) for c, t in zip("ABCDEF", ["immediate action correction", "static images do not stimulate", "actions look effortless", "training changes the brain", "internalise others’ actions", "ignore crowd distractions"])]
    for i, (text, ans) in enumerate(zip(["Expert movements ingrained in premotor cortex", "Goal-oriented movement needed", "Anterior cingulate detects errors", "Human mirror system is intricate"], "CBAE"), 33): qs.append(q(i, text, ans, implications, kind="matching"))
    for i, (text, ans) in enumerate(zip(["cells known as ___", "movement must be ___", "error-detecting brain area: ___", "visual cues combine with our own ___"], ["mirror neurons", "goal-orientated", "anterior cingulate/anterior cingulate cortex", "motor representations"]), 37): qs.append(q(i, text, ans))
    return qs


def make_exam(number, listening, audio, reading, passage_files, writing_image, task1, task2, map_image=None):
    content = "".join(passage_html(name, marker) for name, marker in passage_files)
    listen = {"title": "Listening", "section_type": "listening", "order": 1, "duration_minutes": 40, "audio_file": f"../../TESTLAR/11/{audio}", "notes": listening_notes(number), "content": "", "questions": listening}
    if map_image:
        listen["question_images"] = {"16": f"images/{map_image}"}
    return {
        "title": f"IELTS Full Mock Test {number}",
        "description": "To‘liq IELTS Academic mock test: Listening, Reading va Writing.",
        "exam_type": "mock", "price": 0, "duration_minutes": 170, "is_active": True,
        "sections": [listen,
            {"title": "Reading", "section_type": "reading", "order": 2, "duration_minutes": 60, "notes": reading_notes(number), "content": content, "questions": reading},
            {"title": "Writing", "section_type": "writing", "order": 3, "duration_minutes": 60, "image": f"images/{writing_image}", "content": "", "questions": [q(1, task1, "", kind="essay"), q(2, task2, "", kind="essay")]},
        ],
    }


def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    # The map is physical PDF page 3 (printed page number 4).  Crop away the
    # instructions and answer lines so phones show the actual map at a useful
    # scale rather than a tiny full-page screenshot.
    from PIL import Image
    rendered = IMAGES / "mock_test_14_clifton_map_page.jpg"
    subprocess.run(["pdftoppm", "-f", "3", "-singlefile", "-jpeg", "-r", "150", str(SOURCE / "Listening 15.pdf"), str(rendered.with_suffix(""))], check=True)
    page = Image.open(rendered)
    page.crop((205, 280, 1055, 1165)).save(IMAGES / "mock_test_14_clifton_map.jpg", quality=92)
    rendered.unlink()
    (IMAGES / "mock_test_14_task1.jpg").write_bytes((SOURCE / "photo_2026-11-14_13-54-44.jpg").read_bytes())
    (IMAGES / "mock_test_15_task1.jpg").write_bytes((SOURCE / "photo_2026-02-04_14-46-36.jpg").read_bytes())
    exam14 = make_exam(14, listening14(), "listening14.mp3", reading14(), [
        ("Passage 1 The Baobabs of Madagascar.pdf", "Questions 1"), ("Passage 2 The Future of Food Packaging.pdf", "Questions 14"), ("Passage 3 Marine Mammals Exhibit Ingenuity.pdf", "Questions 27")], "mock_test_14_task1.jpg", "The table shows residential water use in one country in 1988 and 2008. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.", "Students today can easily find information online, so libraries are no longer necessary. To what extent do you agree or disagree?", "mock_test_14_clifton_map.jpg")
    exam15 = make_exam(15, listening15(), "listening15.mp3", reading15(), [
        ("Passage 1 Sydney Opera House.pdf", "Questions 1"), ("Passage 2 The Role of Errors in Learning.pdf", "Questions 14"), ("Passage 3 How Does Watching Sport Influence the Brain.pdf", "Questions 27")], "mock_test_15_task1.jpg", "The bar chart shows the percentage of the population living in urban areas in six regions in 2003 and estimates for 2030. Summarise the main features and make comparisons.", "The use of social media is replacing face-to-face interaction among many people in society. Do the advantages outweigh the disadvantages?")
    for number, data in [(14, exam14), (15, exam15)]:
        (DATA / f"ielts_full_mock_test_{number}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
