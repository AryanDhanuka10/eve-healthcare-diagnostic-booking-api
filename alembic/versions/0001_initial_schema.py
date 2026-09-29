"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-09-28 12:28:53.742052
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table('diagnostic_centres',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(location)) > 0', name=op.f('ck_diagnostic_centres_location_not_blank')),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_diagnostic_centres_name_not_blank')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_diagnostic_centres')),
    sa.UniqueConstraint('name', 'location', name='uq_diagnostic_centres_name_location')
    )
    op.create_table('diagnostic_tests',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_diagnostic_tests_name_not_blank')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_diagnostic_tests')),
    sa.UniqueConstraint('name', name=op.f('uq_diagnostic_tests_name'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.Enum('USER', 'ADMIN', name='user_role', native_enum=False, create_constraint=True, length=20), server_default='USER', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_users_email_lowercase')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('webhook_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('provider_event_id', sa.String(length=128), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('payment_reference', sa.String(length=64), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('outcome', sa.String(length=30), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_events')),
    sa.UniqueConstraint('provider_event_id', name=op.f('uq_webhook_events_provider_event_id'))
    )
    op.create_table('centre_tests',
    sa.Column('centre_id', sa.Uuid(), nullable=False),
    sa.Column('test_id', sa.Uuid(), nullable=False),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price > 0', name=op.f('ck_centre_tests_price_positive')),
    sa.ForeignKeyConstraint(['centre_id'], ['diagnostic_centres.id'], name=op.f('fk_centre_tests_centre_id_diagnostic_centres'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['test_id'], ['diagnostic_tests.id'], name=op.f('fk_centre_tests_test_id_diagnostic_tests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('centre_id', 'test_id', name=op.f('pk_centre_tests'))
    )
    op.create_index(op.f('ix_centre_tests_test_id'), 'centre_tests', ['test_id'], unique=False)
    op.create_table('bookings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('centre_id', sa.Uuid(), nullable=False),
    sa.Column('test_id', sa.Uuid(), nullable=False),
    sa.Column('appointment_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'CONFIRMED', 'FAILED', 'CANCELLED', name='booking_status', native_enum=False, create_constraint=True, length=20), server_default='PENDING', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_bookings_amount_positive')),
    sa.ForeignKeyConstraint(['centre_id', 'test_id'], ['centre_tests.centre_id', 'centre_tests.test_id'], name='fk_bookings_centre_test_offering', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['centre_id'], ['diagnostic_centres.id'], name=op.f('fk_bookings_centre_id_diagnostic_centres'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['test_id'], ['diagnostic_tests.id'], name=op.f('fk_bookings_test_id_diagnostic_tests'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_bookings_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bookings'))
    )
    op.create_index('ix_bookings_user_created', 'bookings', ['user_id', 'created_at'], unique=False)
    op.create_index('uq_bookings_active_slot', 'bookings', ['user_id', 'centre_id', 'test_id', 'appointment_at'], unique=True, postgresql_where=sa.text("status IN ('PENDING', 'CONFIRMED')"))
    op.create_table('payments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('booking_id', sa.Uuid(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED', name='payment_status', native_enum=False, create_constraint=True, length=20), server_default='PENDING', nullable=False),
    sa.Column('provider_reference', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_payments_amount_positive')),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], name=op.f('fk_payments_booking_id_bookings'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('provider_reference', name=op.f('uq_payments_provider_reference'))
    )
    op.create_index(op.f('ix_payments_booking_id'), 'payments', ['booking_id'], unique=False)
    op.create_index('uq_payments_one_active_per_booking', 'payments', ['booking_id'], unique=True, postgresql_where=sa.text("status IN ('PENDING', 'SUCCESS')"))



def downgrade() -> None:

    op.drop_index('uq_payments_one_active_per_booking', table_name='payments', postgresql_where=sa.text("status IN ('PENDING', 'SUCCESS')"))
    op.drop_index(op.f('ix_payments_booking_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index('uq_bookings_active_slot', table_name='bookings', postgresql_where=sa.text("status IN ('PENDING', 'CONFIRMED')"))
    op.drop_index('ix_bookings_user_created', table_name='bookings')
    op.drop_table('bookings')
    op.drop_index(op.f('ix_centre_tests_test_id'), table_name='centre_tests')
    op.drop_table('centre_tests')
    op.drop_table('webhook_events')
    op.drop_table('users')
    op.drop_table('diagnostic_tests')
    op.drop_table('diagnostic_centres')

