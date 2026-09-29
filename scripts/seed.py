"""Development seed data. Not run automatically on startup — invoke explicitly:

    python -m scripts.seed
"""

import logging

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.centre_test import CentreTest
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.models.enums import UserRole
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed")

CENTRES = [
    {"name": "City Diagnostics", "location": "Connaught Place, New Delhi"},
    {"name": "MedCore Labs", "location": "Bandra, Mumbai"},
    {"name": "Sunrise Pathology", "location": "Koramangala, Bengaluru"},
]

TESTS = [
    {"name": "Complete Blood Count (CBC)", "description": "Evaluates overall blood health."},
    {"name": "Lipid Profile", "description": "Cholesterol and triglyceride levels."},
    {"name": "Thyroid Panel (T3, T4, TSH)", "description": "Thyroid function screen."},
    {"name": "HbA1c", "description": "Average blood glucose over ~3 months."},
    {"name": "Liver Function Test (LFT)", "description": "Liver enzyme and protein levels."},
    {"name": "Chest X-Ray", "description": "Digital chest radiograph."},
]

# (centre index, test index, price) - not every centre offers every test.
OFFERINGS = [
    (0, 0, "350.00"), (0, 1, "650.00"), (0, 2, "899.00"), (0, 5, "450.00"),
    (1, 0, "300.00"), (1, 3, "550.00"), (1, 4, "700.00"),
    (2, 0, "320.00"), (2, 1, "600.00"), (2, 3, "500.00"), (2, 5, "400.00"),
]

ADMIN_EMAIL = "admin@eve-healthcare.test"
ADMIN_PASSWORD = "AdminPass123"


def run() -> None:
    with SessionLocal() as db:
        if db.query(DiagnosticCentre).count() > 0:
            log.info("Seed data already present; skipping.")
            return

        centres = [DiagnosticCentre(**c) for c in CENTRES]
        tests = [DiagnosticTest(**t) for t in TESTS]
        db.add_all(centres + tests)
        db.flush()

        for ci, ti, price in OFFERINGS:
            db.add(CentreTest(centre_id=centres[ci].id, test_id=tests[ti].id, price=price))

        db.add(
            User(
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASSWORD),
                full_name="Admin",
                role=UserRole.ADMIN,
            )
        )
        db.commit()
        log.info("Seeded %d centres, %d tests, %d offerings, 1 admin user.", len(centres), len(tests), len(OFFERINGS))
        log.info("Admin login: %s / %s", ADMIN_EMAIL, ADMIN_PASSWORD)


if __name__ == "__main__":
    run()
