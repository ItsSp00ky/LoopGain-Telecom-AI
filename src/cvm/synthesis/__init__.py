"""Layer 2 -- GAN synthesis engine.  Owner: E1

The public datasets have no concept of a scratch card, a zero-balance night,
Ramadan, or a generator outage. We generate those conditionally on the real
features so joint structure is preserved.

A generator proposes synthetic subscriber rows, a discriminator tries to
separate them from real ones, and the two train adversarially until the
generator wins. The result is a non-existent population of Libyan subscribers
whose joint structure matches the real corpus it learned from.
"""
