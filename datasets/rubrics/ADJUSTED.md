# Adjusted rubrics

Built by tools/build_adjusted_rubrics.py. Each Adjusted rubric keeps every level description of the official rubric word for word (the script checks this). Only two things change:

1. **Context**: a block sent with every essay, between the assignment and the essay, saying who the writers are and which standard to judge against.
2. **Question for the model**: a plain question per criterion, replacing the generic "Which level of this rubric criterion does the essay meet?".

Why: on ELLIPSE and ASAP set 7, nimble ranked essays about as well as a second human rater but scored them about 0.8 levels too low, mostly on language criteria, because the request never said who the writers were.

## ASAP set 7 (patience narrative) Adjusted

Official rubric: ASAP set 7 (patience narrative) (`asap7`)

**Context sent with every essay**

> ABOUT THE WRITERS: US students in grade 7 (age 12 to 13), each writing a short story about patience in class. Score as a trained grade 7 rater would: judge every criterion against what is expected of a grade 7 writer, not against polished adult writing. Take into account how much the student wrote: a longer, developed story with some errors usually deserves more credit than a very short one with none.
>
> NOTES ON THE TEXT: names, places, dates, numbers and some capitalised words were replaced with tokens such as @PERSON1, @LOCATION1, @DATE1, @NUM1 and @CAPS1 when the essays were anonymised. Read each token as a correctly written word and do not count it as an error or as unclear writing. Runs of "???" mark characters that were lost from the data; do not count them as the writer's errors.

| Criterion | Official question | Adjusted question |
|---|---|---|
| Ideas (points doubled) | Which level of this rubric criterion does the essay meet? (generic) | How well does this grade 7 writer's story stay focused on patience and develop it with specific, relevant details? |
| Organization | Which level of this rubric criterion does the essay meet? (generic) | How clearly is this grade 7 writer's story organised, with events and ideas connected in a logical sequence? |
| Style | Which level of this rubric criterion does the essay meet? (generic) | How well does this grade 7 writer use language (word choice and sentence variety) to tell the story, judged against grade 7 expectations and the amount written? |
| Conventions | Which level of this rubric criterion does the essay meet? (generic) | How well does this grade 7 writer control grammar, usage, spelling, capitalisation and punctuation for the grade level? Judge the overall pattern across the whole story: some errors are normal at grade 7. Ignore anonymisation tokens such as @CAPS1. |

## PERSUADE 2.0 holistic (independent) Adjusted

Official rubric: PERSUADE 2.0 holistic (independent) (`persuade_holistic_indy`)

**Context sent with every essay**

> ABOUT THE WRITERS: US students in grades 6 to 12, each writing an argumentative essay on the assignment without a source text. Score as a trained rater of student writing would: the six scores span the full range of school writing, so judge against what students in grades 6 to 12 produce, not against published or adult writing. Most student essays score 2, 3 or 4.

| Criterion | Official question | Adjusted question |
|---|---|---|
| Holistic Rating Form | After reading each essay and completing the analytical rating form, assign a holistic score based on the rubric below. For the following evaluations you will need to use a grading scale between 1 (minimum) and 6 (maximum). As with the analytical rating form, the distance between each grade (e.g., 1-2, 3-4, 4-5) should be considered equal. | Which score from 1 to 6 best describes this student's essay as a whole: its point of view, critical thinking, use of examples and evidence, organisation, language and sentence structure, and conventions? |

## PERSUADE 2.0 holistic (source-based) Adjusted

Official rubric: PERSUADE 2.0 holistic (source-based) (`persuade_holistic_source`)

**Context sent with every essay**

> ABOUT THE WRITERS: US students in grades 6 to 12, each writing an argumentative essay based on a source text they read. Score as a trained rater of student writing would: the six scores span the full range of school writing, so judge against what students in grades 6 to 12 produce, not against published or adult writing. Most student essays score 2, 3 or 4. Using and building on the source text is expected, not copying.

| Criterion | Official question | Adjusted question |
|---|---|---|
| Holistic Rating Form | After reading each essay and completing the analytical rating form, assign a holistic score based on the rubric below. For the following evaluations you will need to use a grading scale between 1 (minimum) and 6 (maximum). As with the analytical rating form, the distance between each grade (e.g., 1-2, 3-4, 4-5) should be considered equal. | Which score from 1 to 6 best describes this student's essay as a whole: its point of view, critical thinking, use of evidence from the source, organisation, language and sentence structure, and conventions? |

## PERSUADE 2.0 argument element effectiveness Adjusted

Official rubric: PERSUADE 2.0 argument element effectiveness (`persuade_elements`)

**Context sent with every essay**

> ABOUT THE WRITERS: US students in grades 6 to 12. You are rating ONE argument element (for example a lead, claim or piece of evidence) taken from a student's argumentative essay; the full essay is included only so you can see how the element fits. Score as a trained rater of student writing would: Adequate is the usual rating for an element that does its job in an ordinary way; keep Effective for elements that are clearly strong and Ineffective for elements that fail at their job. Do not mark an element down for spelling or grammar.

| Criterion | Official question | Adjusted question |
|---|---|---|
| Lead | Which level of this rubric criterion does the essay meet? (generic) | Does this lead catch the reader's attention and point towards the writer's position? |
| Position | Which level of this rubric criterion does the essay meet? (generic) | Does this position take a clear stance that is closely related to the topic? |
| Claim | Which level of this rubric criterion does the essay meet? (generic) | How relevant is this claim to the writer's position, and how well does it back the position up? |
| Counterclaim | Which level of this rubric criterion does the essay meet? (generic) | Is this counterclaim a reasonable, relevant objection to the writer's position? |
| Rebuttal | Which level of this rubric criterion does the essay meet? (generic) | How directly and convincingly does this rebuttal answer the counterclaim? |
| Evidence | Which level of this rubric criterion does the essay meet? (generic) | How relevant and sound is this evidence for the claim it supports? |
| Concluding summary | Which level of this rubric criterion does the essay meet? (generic) | How well does this concluding statement restate or pull together the essay's claims? |

## ELLIPSE English proficiency Adjusted

Official rubric: ELLIPSE English proficiency (`ellipse`)

**Context sent with every essay**

> ABOUT THE WRITERS: English language learners in grades 8 to 12 at US schools, each writing an argumentative essay on the assignment. Score as a trained rater of English learners would: judge every criterion against the range of writing seen in English learners at this stage, not against native speakers or adult writers. Level 3 is the typical, middle performance for these learners; use levels 4 and 5 for writers who show real control and range even if some errors remain. Judge errors by how often they occur across the whole essay and whether they get in the way of meaning, not by counting every slip.

| Criterion | Official question | Adjusted question |
|---|---|---|
| Overall | Which level of this rubric criterion does the essay meet? (generic) | Overall, how well does this English learner use English to communicate their argument? |
| Cohesion | Which level of this rubric criterion does the essay meet? (generic) | How well does this English learner organise the essay and connect ideas within and across sentences and paragraphs? |
| Syntax | Which level of this rubric criterion does the essay meet? (generic) | How varied and accurate are this English learner's sentence structures? |
| Vocabulary | Which level of this rubric criterion does the essay meet? (generic) | How wide and accurate is this English learner's vocabulary for the topic? |
| Phraseology | Which level of this rubric criterion does the essay meet? (generic) | How varied and accurate are this English learner's multi-word phrases (idioms, collocations and set expressions)? |
| Grammar | Which level of this rubric criterion does the essay meet? (generic) | How accurate is this English learner's grammar and usage, judged across the whole essay and relative to its length? |
| Conventions | Which level of this rubric criterion does the essay meet? (generic) | How well does this English learner control spelling, capitalisation and punctuation, judged across the whole essay and relative to its length? |

