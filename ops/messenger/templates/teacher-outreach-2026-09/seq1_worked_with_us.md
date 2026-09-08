# Sequence 1: Worked With Us (HubSpot list 3210, 159 teachers)

Rail: HubSpot Sequence from Danielle's connected inbox. Business days, 9am to
5pm PT. Email 2 threads as a reply to email 1. Exit on reply, on
`campaign_replied = Yes`, on Teacher Scholarship form submission, and on a new
charter deal naming the teacher. No call step, no meeting link (Roman
2026-09-03). Top 30 by deal $ (list 3214) get a hand-written day-10 note from
Danielle if silent; everyone else is done after email 2.

Every student has funds; never say "students with funds." The school issues the
PO; never say "we handle the PO." No em dashes.

Signature on both emails:

```
Danielle Brodetsky
Director of School Partnerships, A+ Tutoring
Tutoring Program Design Badge, National Student Support Accelerator at Stanford University, 2026 to 2029
```

---

## Email 1, day 0

**Subject:** {{contact.firstname}}, your A+ families from last year

Hi {{contact.firstname}},

Several of your families tutored with A+ last year, and I want to make sure none of them fall through the cracks as funds get allocated.

If any of them are continuing, or there's a new student on your caseload who could use a tutor this year, reply with the name. I'll send you the vendor details and hours to put on the PO, and once the school issues it we take everything from there: tutor match, scheduling, and progress updates all year.

One update since we last worked together: this summer Stanford's National Student Support Accelerator reviewed the way we tutor and awarded us its Tutoring Program Design Badge. You're welcome to pass that along to parents.

Want a quick list of who tutored with us? Just say "send it."

Danielle

---

## Email 2, day 5, threaded, only if no reply

**Subject:** One name is enough

Hi {{contact.firstname}},

No need to send a list. If one student comes to mind who could use a tutor this year, reply with their name. I'll send back exactly what to put on the PO, and you're done.

And for a family that hasn't decided yet: our Teacher Scholarship Program lets a student try us with a real tutor, live and one-on-one, without touching their allocation. If you'd rather hand that to a family than ask them to commit, nominate the student here and I'll take it from there: [Nominate a student]

If nobody comes to mind right now, that's a good answer too. I'll check back in October when the next PO cycle opens.

Danielle

---

## Day 10, hand-written by Danielle, top 30 only, if silent

Two lines, in the same thread. Name one of their families from the roster
(scripts/teacher_roster.py) and ask if that family is coming back. Nothing else.

---

Links: [Nominate a student] = https://share.hsforms.com/2rpbTDqE6RWWHjeKdFnEFgA3ray8
Roster on "send it": `python3 scripts/teacher_roster.py <teacher email>`
