#!/usr/bin/env python3
"""Build IELTS Full Mock Test 16 from the source pack in TESTLAR/12."""
from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TESTLAR" / "12"
DATA = ROOT / "data" / "cambridge"
IMAGES = DATA / "images"


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


def pdf_text(path, first=None, last=None):
    command = ["pdftotext", "-layout"]
    if first:
        command += ["-f", str(first)]
    if last:
        command += ["-l", str(last)]
    command += [str(path), "-"]
    return subprocess.check_output(command, text=True).replace("\f", "\n")


def paragraphs(title, raw):
    # Preserve source paragraph breaks. A single wall of text is especially
    # difficult to read in the split-screen exam view on phones.
    raw = raw.strip()
    flexible_title = r"\s+".join(re.escape(word) for word in title.split())
    raw = re.sub(rf"^\s*{flexible_title}\s*", "", raw, count=1, flags=re.I)
    raw = raw.replace("Dares Salaam", "Dar es Salaam")
    blocks = re.split(r"\n\s*\n", raw)
    rendered = []
    for block in blocks:
        lines = []
        for line in block.splitlines():
            line = line.strip()
            if not line or re.fullmatch(r"\d+", line) or line in {"Reading", "Test 3"}:
                continue
            lines.append(line)
        subheading = ""
        if lines and lines[0] in {
            "Packaging", "Design considerations", "Safety and compliance",
            "Design principles and guidelines", "Innovation",
        }:
            subheading = f"<h3>{html.escape(lines.pop(0))}</h3>"
        text = re.sub(r"(?<=\w)- (?=\w)", "", " ".join(lines))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            rendered.append(subheading + f"<p>{html.escape(text)}</p>")
    return f"<h2>{html.escape(title)}</h2>" + "".join(rendered)


def reading_content():
    passage1 = pdf_text(SOURCE / "Passage 1 Think Small.pdf").split("Think Small", 1)[1]
    passage1 = passage1.split("Questions 1", 1)[0]

    book = pdf_text(SOURCE / "@cdireport IELTS 21.pdf")
    start = book.index("The problems of getting around the city of")
    end = book.index("Questions   14-18", start)
    passage2 = book[start:end]

    # This scan has no text layer, so its two passage pages are transcribed here.
    passage3 = """
Packaging
One of the most prominent design issues in pharmacy is that of drug packages and the patient information leaflets (PILs) included in them. Many pharmacists are concerned that current designs are 'accidents waiting to happen'. The UK government shares this concern and, in 2003, the National Patient Safety Agency created a new role, appointing Colum Lowe, who has 14 years' experience as a designer in the private sector, as head of design and human factors.

Packaging design in the pharmaceutical industry is handled by either in-house teams or external design agencies. For packaging design of over-the-counter medicines, which do not have to be dispensed by a pharmacist but can be bought directly from a sales assistant, characteristics such as attractiveness and distinguishability are important and so these are usually commissioned from an external design team. The marketing team prepares the initial brief and the designers come up with six or seven designs. Two or three of these are then tested on a consumer group. In contrast, most designs for prescription-only products are created in-house. In some cases, this may simply involve the company's design team applying the house design and then handing it over to design engineers rather than testing the design on a consumer group. Clearly this process cannot adequately address the needs of the wide variety of patients using medication.

Design considerations
In her book Information Design for Patient Safety, Thea Swayne highlighted a multitude of design problems. For example, drugs that look or sound alike can lead to confusion, small type sizes and even the glare on silver foil packaging can lead to names or instructions being misread. One such example is a drug that was accidentally injected into a patient through the spine (intrathecally) rather than through the veins (intravenously). Investigations following this tragedy attributed some blame to the poor choice of typescript used on the drug container. Furthermore, according to Swayne, real situations in which medicines are used include a parent giving a cough medicine to a child in the middle of the night; packaging should be designed for moments such as these rather than for the ideal world of a hospital.

Safety and compliance
Child protection is another area that gives designers opportunities to improve safety. According to the Child Accident Prevention Trust, 70% of children admitted to hospital with suspected poisoning have swallowed medicines, and although child-resistant lids have helped, they are not yet fully effective. There is scope for improving what is currently available, according to Richard Mawle, a freelance product designer who feels it is not just children who are blocked by child-proof closures. Many child-resistant packs are based on strength but older people may have the same level of strength as a child, he explained, and suggested that better designs could rely on cognitive skills, for example removing the lid using a three-step process.

Mawle also worked on a project which involved applying his skills to packaging and PILs. Commenting on the information presented, he said there can be an awful lot of junk at the beginning of PILs. For example, why are company details towards the beginning of a leaflet when what might be more vital for the patient is that the medicine should not be taken with alcohol?

Design principles and guidelines
Most designers work according to basic principles; for example, certain print styles are known to be more difficult to read than others. Look-alike boxes present the potential for errors and an obvious solution would be to use colour to highlight a larger dosage of a drug. However, according to Thea Swayne, designating a colour to a particular dosage is not recommended because this could lead to the user not reading the text on a box.

Design features can provide the basis for lengthy debates. One argument is that if all packaging was white with black lettering, people would have no choice but to read every box carefully. The problem is that trials of drug packaging are few. Although some designers take results from signage studies into account, proving that a particular feature is beneficial can be difficult. Current UK legislation requires packaging to include the name of the medicine in Braille, but, according to Karel van der Waarde, a design consultant to the pharmaceutical industry, it is not known how much visually impaired patients will benefit nor how much the reading of visually able patients will be impaired. Van der Waarde is sceptical about current legislation and says that many regulatory authorities do not have the resources to handle packaging information properly. They do not look at the use of packaging in a practical context; they only see one box at a time and not several together as pharmacists would do.

Innovation
On a positive note, a recent innovation exhibition revealed several new designs. 'The popper' aims to help arthritis sufferers remove tablets from blister packs, and 'Pluspoint' is an adrenaline auto-injector aimed at overcoming the fact that many patients do not carry their medication due to its prohibitive size. The aim of good design is to try to make things more user-friendly as well as safer. The guidelines in Information Design for Patient Safety are not intended to be legally binding. Rather, the book's purpose is to create a basic design standard and to stimulate innovation. The challenge for the pharmaceutical industry is to adopt such a standard.
"""
    return (
        paragraphs("Think Small", passage1)
        + paragraphs("The problems of getting around the city of Dar es Salaam", passage2)
        + paragraphs("Improving Patient Safety", passage3)
    )


def listening_questions():
    qs = []
    answers = ["65", "40", "photo", "Rosie", "Saturday", "discount", "museum", "box", "ocean", "camp"]
    prompts = [
        "A family ticket is $___", "The fastest bus takes about ___ minutes",
        "You can hold some animals and have a ___ for a small fee", "John ___ is performing",
        "Performances run from Tuesday to ___", "There is a ___ on tickets for Monday night's preview",
        "Go to the city centre ___ to see a special exhibition", "For origami, take a small ___",
        "Salty Lake is on the ___ side of Bunyabbie Island", "You are not allowed to ___ on the island",
    ]
    for order, (prompt, answer) in enumerate(zip(prompts, answers), 1):
        prefix = "[Places to visit with children] Complete the notes. Write ONE WORD AND/OR A NUMBER.\n" if order == 1 else ""
        qs.append(question(order, prefix + prompt, answer))

    roles = [("A", "An office will be provided for this role"), ("B", "More than one person is needed for this role"),
             ("C", "This is a new role for this year's fair"), ("D", "This role will start next month"),
             ("E", "This role will mainly involve evening work"), ("F", "You need your own transport")]
    for order, (role, answer) in enumerate(zip(["Entertainment co-ordinator", "Advertising and promotion co-ordinator", "Technical co-ordinator", "Staffing co-ordinator"], "EBFC"), 11):
        prefix = "[School fair volunteer roles] Match each role to the correct comment.\n" if order == 11 else ""
        qs.append(question(order, prefix + role, answer, roles, "matching"))

    map_choices = [(letter, "") for letter in "ABCDEFGHI"]
    for order, (place, answer) in enumerate(zip(["Fairground rides", "Entertainment stage", "Café", "First aid tent", "Market stalls", "Pony rides"], "IDAH EB".replace(" ", "")), 15):
        prefix = "[School fair map] Label the map.\n" if order == 15 else ""
        qs.append(question(order, prefix + place, answer, map_choices, "matching"))

    opinions = [(letter, text) for letter, text in zip("ABCDEFGHI", [
        "was surprisingly interesting", "covered too many topics", "included out-of-date materials",
        "involved practical applications", "supplied useful technical information", "was too basic to be useful",
        "provided unnecessary detail", "was relevant to a topic in the news", "seemed too limited geographically",
    ])]
    modules = ["Statistics for environmental research", "Sewage and drainage systems", "Agriculture and food security", "Sustainable energy", "Government policy", "Water management"]
    for order, (module, answer) in enumerate(zip(modules, "FACDIG"), 21):
        prefix = "[Environmental Science modules] Match each module to the student's opinion.\n" if order == 21 else ""
        qs.append(question(order, prefix + module, answer, opinions, "matching"))

    course = [("A", "the amount of reading"), ("B", "flexibility in the length of the course"),
              ("C", "convenience of choosing when to take modules"), ("D", "range of modules offered"),
              ("E", "relevance of the module content")]
    for order, answer in zip((27, 28), "DE"):
        qs.append(question(order, ("Which TWO aspects of the course organisation did both students like?" if order == 27 else "Select the second answer."), answer, course))
    suggestions = [("A", "Change the time for choosing a topic"), ("B", "Increase the permitted word limit"),
                   ("C", "Arrange discussions with fellow students"), ("D", "Schedule face-to-face tutor feedback"),
                   ("E", "Give more help in topic selection")]
    for order, answer in zip((29, 30), "AC"):
        qs.append(question(order, ("Which TWO suggestions for written assignments do they recommend?" if order == 29 else "Select the second answer."), answer, suggestions))

    final_prompts = ["has written many ___", "award in 2011 for ___ in music", "music often features ___",
                     "violin sounds resemble those found in ___", "seen as a ___ of music", "music compared to a distant ___",
                     "written in memory of a ___", "noise sounds like ___", "made by moving large pieces of ___", "has a traditional ___"]
    final_answers = ["essays", "originality", "silence", "nature", "pioneer", "volcano", "friend", "thunder", "metal", "structure"]
    for order, (prompt, answer) in enumerate(zip(final_prompts, final_answers), 31):
        prefix = "[The Music of Salvatore Sciarrino] Complete the notes. Write ONE WORD ONLY.\n" if order == 31 else ""
        qs.append(question(order, prefix + prompt, answer))
    return qs


def reading_questions():
    qs = []
    tf = [(x, x.title()) for x in ("TRUE", "FALSE", "NOT GIVEN")]
    p1 = [
        "Izon's new US headquarters are located in an area popular with other science businesses.",
        "Izon's growth in the last three years has been faster than the company predicted.",
        "Since 2004, Izon has developed a range of equipment for scientific research.",
        "One advantage of the qNano is that it is cheaper than its competitors.",
        "Drug delivery analysis will be the most profitable application of the qNano.",
        "Kristoffer Bolen is still completing his studies.", "Bolen's job requires him to fully understand how the qNano works.",
    ]
    for order, (prompt, answer) in enumerate(zip(p1, ["TRUE", "NOT GIVEN", "FALSE", "NOT GIVEN", "NOT GIVEN", "TRUE", "TRUE"]), 1):
        prefix = "[Think Small] TRUE, FALSE or NOT GIVEN.\n" if order == 1 else ""
        qs.append(question(order, prefix + prompt, answer, tf))
    notes = [("He made the ___ which enabled the prototype to be created.", "investment"),
             ("His background in ___ and business gave him the skills to run Izon.", "engineering"),
             ("Marketing relies on ___ about customers' research.", "articles"),
             ("Yaniv Gaynor was formerly a ___, with no sales experience.", "teacher"),
             ("To diagnose thrombosis, a ___ may be developed.", "test"),
             ("___ will be done at Izon's US headquarters.", "training")]
    for order, (prompt, answer) in enumerate(notes, 8):
        qs.append(question(order, ("Complete the notes. Choose ONE WORD ONLY.\n" if order == 8 else "") + prompt, answer))

    p2 = ["The population is rising more rapidly than previously predicted.", "Most residents live in high-rise blocks on the edge of the city.",
          "Residents have been consulted about the suburban rail line.", "The majority of present residential development is unplanned.",
          "The authorities followed a public transport plan adopted by many African cities."]
    for order, (prompt, answer) in enumerate(zip(p2, ["NOT GIVEN", "FALSE", "NOT GIVEN", "TRUE", "FALSE"]), 14):
        prefix = "[Dar es Salaam] TRUE, FALSE or NOT GIVEN.\n" if order == 14 else ""
        qs.append(question(order, prefix + prompt, answer, tf))
    p2_notes = [("buses use designated ___ to cut down on delays", "lanes"), ("passengers pay fares before ___", "boarding"),
                ("passengers in ___ can use every part of the system", "wheelchairs"), ("temperature control is not activated to reduce ___ use", "fuel"),
                ("vehicle shortage followed a severe ___", "flood"), ("passengers cannot use ___ because readers are broken", "smartcards"),
                ("tickets are checked manually at station ___", "gates"), ("___ build up during rush hours", "queues")]
    for order, (prompt, answer) in enumerate(p2_notes, 19):
        qs.append(question(order, ("Complete the notes. Choose ONE WORD ONLY.\n" if order == 19 else "") + prompt, answer))

    people = [("A", "Thea Swayne"), ("B", "The Child Accident Prevention Trust"), ("C", "Richard Mawle"), ("D", "Karel van der Waarde")]
    statements = ["Elderly people need containers that do not require force to open.", "Adapting packaging for blind people may disadvantage sighted people.",
                  "Specially designed containers have not eliminated accidental swallowing.", "Designers must consider how drugs are used at home.",
                  "Governing bodies need to compare different containers.", "Medicine information is not listed in the right order."]
    for order, (prompt, answer) in enumerate(zip(statements, "CDBADC"), 27):
        prefix = "[Improving Patient Safety] Match each statement to a person or group.\n" if order == 27 else ""
        qs.append(question(order, prefix + prompt, answer, people, "matching"))
    word_bank = [("A", "consumers"), ("B", "design engineers"), ("C", "external design team"), ("D", "in-house design team"), ("E", "marketing team"), ("F", "pharmaceutical industry"), ("G", "pharmacists")]
    summary = ["The initial proposal is written by the ...", "Several designs are produced by the ...", "Selected designs are shown to ...", "For prescription-only drugs, the ... create the design.", "The design is then passed to ..."]
    for order, (prompt, answer) in enumerate(zip(summary, "ECADB"), 33):
        prefix = "Complete the summary using the list A-G.\n" if order == 33 else ""
        qs.append(question(order, prefix + prompt, answer, word_bank, "matching"))
    mcqs = [
        ("What design consideration caused a drug to be given incorrectly?", "B", [("A", "a printing error"), ("B", "the style of print"), ("C", "an incorrect label"), ("D", "the bottle shape")]),
        ("What is said about using only black and white?", "C", [("A", "Consumers would dislike it"), ("B", "Containers would look too similar"), ("C", "People would pay more attention to labels"), ("D", "Partially sighted people would find it helpful")]),
        ("Why are 'the popper' and 'Pluspoint' mentioned?", "A", [("A", "to show progress in pharmaceutical packaging design"), ("B", "to show design problems that cause accidents"), ("C", "to prove much more work is needed"), ("D", "to show patients need more product information")]),
    ]
    for order, (prompt, answer, choices) in enumerate(mcqs, 38):
        qs.append(question(order, prompt, answer, choices))
    return qs


def listening_notes():
    return {
        "1": "<h5>Places to visit with children</h5><p><strong>Alma Park</strong></p><ul><li>A family ticket is $[[1]]</li><li>The fastest bus takes about [[2]] minutes</li><li>Hold some animals and have a [[3]] for a small fee</li></ul><p><strong>The Entertainment Room</strong></p><ul><li>John [[4]] is performing</li><li>Performances run from Tuesday to [[5]]</li><li>There is a [[6]] on tickets for Monday night's preview</li></ul><p><strong>The City</strong></p><ul><li>Go to the city centre [[7]] to see a special exhibition</li><li>For origami, take a small [[8]]</li></ul><p><strong>Bunyabbie Island</strong></p><ul><li>Salty Lake is on the [[9]] side</li><li>You are not allowed to [[10]] on the island</li></ul>",
        "31": "<h5>The Music of Salvatore Sciarrino</h5><p><strong>Work</strong></p><ul><li>He has written many [[31]]</li><li>Won a 2011 award for [[32]] in music</li></ul><p><strong>Musical characteristics</strong></p><ul><li>Music often features [[33]] and very soft sounds</li><li>Violin sounds resemble those in [[34]]</li><li>Seen as a [[35]] of music</li><li>Compared to a distant [[36]]</li></ul><p><strong>Concert piece</strong></p><ul><li>Written in memory of a [[37]]</li><li>Starts with a sound like [[38]], made by moving large pieces of [[39]]</li><li>Has a traditional [[40]]</li></ul>",
    }


def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    (IMAGES / "mock_test_16_task1.jpg").write_bytes((SOURCE / "photo_2026-11-22_07-12-01.jpg").read_bytes())
    # The school-fair plan is on physical page 3 of the listening booklet.
    rendered = IMAGES / "mock_test_16_school_fair_page.jpg"
    subprocess.run(["pdftoppm", "-f", "3", "-singlefile", "-jpeg", "-r", "170", str(SOURCE / "test 25.pdf"), str(rendered.with_suffix(""))], check=True)
    from PIL import Image
    page = Image.open(rendered)
    page.crop((215, 330, 1110, 1065)).save(IMAGES / "mock_test_16_school_fair_map.jpg", quality=92)
    rendered.unlink()

    exam = {
        "title": "IELTS Full Mock Test 16",
        "description": "To‘liq IELTS Academic mock test: Listening, Reading va Writing.",
        "exam_type": "mock", "price": 0, "duration_minutes": 170, "is_active": True,
        "sections": [
            {"title": "Listening", "section_type": "listening", "order": 1, "duration_minutes": 40,
             "audio_file": "../../TESTLAR/12/listening16.mp3", "notes": listening_notes(), "content": "",
             "question_images": {"15": "images/mock_test_16_school_fair_map.jpg"}, "questions": listening_questions()},
            {"title": "Reading", "section_type": "reading", "order": 2, "duration_minutes": 60,
             "content": reading_content(), "questions": reading_questions()},
            {"title": "Writing", "section_type": "writing", "order": 3, "duration_minutes": 60,
             "image": "images/mock_test_16_task1.jpg", "content": "", "questions": [
                 question(1, "The table shows the percentage of the population who rode bicycles in one town by age group in 2012. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.", "", kind="writing_task", word_limit=150),
                 question(2, "Nowadays, an increasing number of people with health problems are using alternative medicines and treatments instead of visiting their normal doctor. Do you think this is a positive or negative development?", "", kind="writing_task", word_limit=250),
             ]},
        ],
    }
    (DATA / "ielts_full_mock_test_16.json").write_text(json.dumps(exam, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
