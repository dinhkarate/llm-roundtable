# Which database should the new booking service use?

We are building a booking service for a chain of 40 clinics. It goes live in 10 weeks with a team of four
backend engineers, all comfortable with SQL; one has run PostgreSQL in production, nobody has run MongoDB.

Workload estimates (from the current paper process):
- about 30,000 bookings per day at peak, reads roughly 10x writes
- a booking touches a patient, a clinician, a room and a time slot; double booking must be impossible
- reporting needs joins across bookings, clinicians and clinics, run nightly
- data must stay in the EU; the company already has a managed PostgreSQL contract with its cloud provider

What matters most: no double bookings, a team that can operate it at 3 a.m., and shipping on time.

## Options
- A: PostgreSQL (managed, existing contract), with an exclusion constraint on clinician/room time ranges
- B: MongoDB Atlas, with application-level locking for slots
- C: PostgreSQL for bookings plus Redis for slot holds during checkout
