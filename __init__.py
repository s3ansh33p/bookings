# create admin route for viewing submitted presentations

from flask import Blueprint, request, render_template # only needed for Blueprint import
from flask_restx import Namespace, Resource
from CTFd.models import db, Teams
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.plugins.migrations import upgrade
from CTFd.api import CTFd_API_v1

from CTFd.plugins import register_plugin_assets_directory

# for datetime parsing
from datetime import datetime

bookings_namespace = Namespace("bookings", description="Endpoint for booking system")

class Workshop(db.Model):
    # stores name, description
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    description = db.Column(db.Text)
    day = db.Column(db.Integer)

    def __init__(self, name, description, day):
        self.name = name
        self.description = description
        self.day = day

    def __repr__(self):
        return "<Workshop {0} - {1} - {2}>".format(self.id, self.name, self.description, self.day)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "day": self.day
        }
    
class Booking(db.Model):
    # stores team_id, booking_time, notes
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer)
    booking_time = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    workshop_id = db.Column(db.Integer)

    def __init__(self, team_id, booking_time, notes, type_id):
        self.team_id = team_id
        self.booking_time = booking_time
        self.notes = notes
        self.workshop_id = type_id

    def __repr__(self):
        return "<Booking {0} for team {1} at {2}>".format(self.id, self.team_id, self.booking_time)
    
    def serialize(self):
        # custom serialize datetime object to string
        booking_time = self.booking_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        return {
            "id": self.id,
            "team_id": self.team_id,
            "booking_time": booking_time,
            "notes": self.notes,
            "type_id": self.workshop_id
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
        if not data.get("type_id"):
            return {"success": False, "error": "Missing type_id"}, 400

        parsed_datetime = datetime.strptime(data.get("booking_time"), '%Y-%m-%dT%H:%M:%S.%fZ')

        # check if booking already exists
        booking = Booking.query.filter_by(workshop_id=data.get("type_id"), booking_time=parsed_datetime).first()
        if booking:
            return {"success": False, "error": "Booking already exists"}, 400
        
        # # a team can only have one booking per time on the same day
        # bookings = Booking.query.filter_by(team_id=data.get("team_id")).all()
        # for booking in bookings:
        #     # check if booking is on the same day
        #     print(booking.booking_time.date(), parsed_datetime.date(), booking.booking_time.time(), parsed_datetime.time())
        #     if booking.booking_time.date() == parsed_datetime.date():
        #         # check if booking is on the same time
        #         if booking.booking_time.time() == parsed_datetime.time():
        #             return {"success": False, "error": "Team already has a booking at this time"}, 400

        # a team can have a maximum of 4 bookings per day
        bookings = Booking.query.filter_by(team_id=data.get("team_id")).all()
        count = 0
        for booking in bookings:
            # check if booking is on the same day
            if booking.booking_time.date() == parsed_datetime.date():
                count += 1
                print(count, repr(booking), parsed_datetime.date())
        if count >= 4:
            return {"success": False, "error": "Your team already has 2 hours worth of bookings for this day"}, 400

        # create new booking
        booking = Booking(
            team_id=data.get("team_id"),
            booking_time=parsed_datetime,
            notes=data.get("notes"),
            type_id=data.get("type_id")
        )

        # add booking to database
        db.session.add(booking)
        db.session.commit()

        return {"success": True, "data": repr(booking)}
    
    # route to delete a booking
    @authed_only
    def delete(self):
        # delete a booking from type_id and time
        # parses request arguements into data
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        # check for fields
        if not data.get("type_id"):
            return {"success": False, "error": "Missing type_id"}, 400
        if not data.get("booking_time"):
            return {"success": False, "error": "Missing booking_time"}, 400
        
        # get booking from database
        booking = Booking.query.filter_by(workshop_id=data.get("type_id"), booking_time=data.get("booking_time")).first()

        # if not found, return error
        if not booking:
            return {"success": False, "error": "Booking not found"}, 400

        # delete booking from database
        db.session.delete(booking)
        db.session.commit()

        return {"success": True}
    
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
        # make bookings serializable
        bookings = [booking.serialize() for booking in bookings]
        return {"success": True, "data": bookings}

# route to delete all bookings for admins
@bookings_namespace.route("/delete")
class BookingDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all bookings.
    """
    # user must be admin
    @admins_only
    def delete(self):
        # delete all bookings from database
        bookings = Booking.query.all()
        for booking in bookings:
            db.session.delete(booking)
        db.session.commit()
        return {"success": True}

# route to create new booking types
@bookings_namespace.route("/types")
class Workshops(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to create a new booking type.
    This could be for a workshop for example
    """

    # user must be admin
    @admins_only
    def post(self):
        # parses request arguements into data
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        # check for fields
        if not data.get("name"):
            return {"success": False, "error": "Missing name"}, 400
        if not data.get("description"):
            return {"success": False, "error": "Missing description"}, 400
        if not data.get("day"):
            return {"success": False, "error": "Missing day"}, 400

        # create new booking type
        booking_type = Workshop(
            name=data.get("name"),
            description=data.get("description"),
            day=data.get("day")
        )

        # add booking type to database
        db.session.add(booking_type)
        db.session.commit()

        return {"success": True, "data": repr(booking_type)}

    # get all booking types
    @authed_only
    def get(self):
        # query by day
        if request.args.get("day"):
            # get all booking types from database
            booking_types = Workshop.query.filter_by(day=request.args.get("day")).all()
            # make booking types serializable
            booking_types = [booking_type.serialize() for booking_type in booking_types]
            return {"success": True, "data": booking_types}
        else:
            # get all booking types from database
            booking_types = Workshop.query.all()
            # make booking types serializable
            booking_types = [booking_type.serialize() for booking_type in booking_types]
            return {"success": True, "data": booking_types}
    
    # delete a booking type
    @admins_only
    def delete(self):
        # parses request arguements into data
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        # check for fields
        if not data.get("id"):
            return {"success": False, "error": "Missing id"}, 400

        # get booking type from database
        booking_type = Workshop.query.filter_by(id=data.get("id")).first()

        # delete booking type from database
        db.session.delete(booking_type)
        db.session.commit()

        return {"success": True, "data": repr(booking_type)}
    
    # update a booking type with put
    @admins_only
    def put(self):
        # parses request arguements into data
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        # check for fields
        if not data.get("id"):
            return {"success": False, "error": "Missing id"}, 400
        if not data.get("name"):
            return {"success": False, "error": "Missing name"}, 400
        if not data.get("description"):
            return {"success": False, "error": "Missing description"}, 400
        if not data.get("day"):
            return {"success": False, "error": "Missing day"}, 400

        # get booking type from database
        booking_type = Workshop.query.filter_by(id=data.get("id")).first()

        # update booking type
        booking_type.name = data.get("name")
        booking_type.description = data.get("description")
        booking_type.day = data.get("day")

        # commit changes to database
        db.session.commit()

        return {"success": True, "data": repr(booking_type)}    

# register types/delete to delete all types with admin rights
@bookings_namespace.route("/types/delete")
class WorkshopsDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all booking types.
    """

    # user must be admin
    @admins_only
    def delete(self):
        # delete all booking types from database
        booking_types = Workshop.query.all()
        for booking_type in booking_types:
            db.session.delete(booking_type)
        db.session.commit()
        return {"success": True}

# route to view all team names and team_ids, even if hidden
@bookings_namespace.route("/teams")
class BookingTeams(Resource):
    """
    The Purpose of this API Endpoint is to allow a guest to view all teams.
    """

    @authed_only
    def get(self):
        # get all teams from database
        teams = Teams.query.all()
        # only return id and name
        teams = [{"id": team.id, "name": team.name} for team in teams]
        return {"success": True, "data": teams}

def load(app):

    # drop table workshops
    # Workshop.__table__.drop(app.db.engine)

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
    
    # add user route for mentor bookings
    @app.route("/bookings/mentors", methods=['GET'])
    @authed_only
    def bookings_mentor_listing():
        return render_template('plugins/bookings/assets/mentor.html')

    # add route for guest mentors to view bookings
    @app.route("/bookings/view", methods=['GET'])
    def bookings_view_listing():
        return render_template('plugins/bookings/assets/view.html')