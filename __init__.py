# create admin route for viewing submitted presentations

from flask import Blueprint, request, render_template # only needed for Blueprint import
from flask_restx import Namespace, Resource
from CTFd.models import db
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.plugins.migrations import upgrade
from CTFd.api import CTFd_API_v1

from CTFd.plugins import register_plugin_assets_directory

# for datetime parsing
from datetime import datetime

bookings_namespace = Namespace("bookings", description="Endpoint for booking system")

class Booking(db.Model):
    # stores team_id, booking_time, notes
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer)
    booking_time = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    def __init__(self, team_id, booking_time, notes):
        self.team_id = team_id
        self.booking_time = booking_time
        self.notes = notes

    def __repr__(self):
        return "<Booking {0} for team {1} at {2}>".format(self.id, self.team_id, self.booking_time)
    
    def serialize(self):
        # custom serialize datetime object to string
        booking_time = self.booking_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        return {
            "id": self.id,
            "team_id": self.team_id,
            "booking_time": booking_time,
            "notes": self.notes
        }
    
@bookings_namespace.route("")
class BookingAdd(Resource):
    """
	The Purpose of this API Endpoint is to allow a user to add a new booking to the database.
	"""
    # user has to be authentificated to call this endpoint    
    @authed_only
    def post(self):
        # parses request arguements into data
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        # check for fields
        if not data.get("team_id"):
            return {"success": False, "error": "Missing team_id"}, 400
        if not data.get("booking_time"):
            return {"success": False, "error": "Missing booking_time"}, 400
        if not data.get("notes"):
            return {"success": False, "error": "Missing notes"}, 400

        parsed_datetime = datetime.strptime(data.get("booking_time"), '%Y-%m-%dT%H:%M:%S.%fZ')

        # create new booking
        booking = Booking(
            team_id=data.get("team_id"),
            booking_time=parsed_datetime,
            notes=data.get("notes")
        )

        # print booking to console
        print('\n')
        print(repr(booking))
        print('\n')

        # add booking to database
        db.session.add(booking)
        db.session.commit()

        return {"success": True, "data": repr(booking)}
    
# route to view bookings
@bookings_namespace.route("/view")
class BookingView(Resource):
    """
    The Purpose of this API Endpoint is to allow a user to view all bookings.
    """
    # user has to be authentificated to call this endpoint    
    @authed_only
    def get(self):
        # get all bookings from database
        bookings = Booking.query.all()
        # print bookings to console
        print(bookings)
        # make bookings serializable
        bookings = [booking.serialize() for booking in bookings]
        return {"success": True, "data": bookings}

def load(app):
    upgrade()
    app.db.create_all()
    register_plugin_assets_directory(app, base_path="/plugins/bookings/assets/")
    CTFd_API_v1.add_namespace(bookings_namespace, '/bookings')

    # # add admin route
    @app.route("/admin/bookings", methods=['GET'])
    @admins_only
    def admin_bookings_listing():
        return render_template('plugins/bookings/assets/admin.html')

    # add user route
    @app.route("/bookings", methods=['GET'])
    @authed_only
    def bookings_listing():
        return render_template('plugins/bookings/assets/user.html')
    