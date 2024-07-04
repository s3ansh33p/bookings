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


class SessionType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)

    def __init__(self, name, start_date, end_date):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date

    def __repr__(self):
        return "<SessionType {0} - {1} - {2} - {3}>".format(self.id, self.name, self.start_date, self.end_date)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat()
        }

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    description = db.Column(db.Text)
    session_type = db.Column(db.Integer)

    def __init__(self, name, description, session_type):
        self.name = name
        self.description = description
        self.session_type = session_type

    def __repr__(self):
        return "<Workshop {0} - {1} - {2} - {3}>".format(self.id, self.name, self.description, self.session_type)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "session_type": self.session_type
        }
    
class Booking(db.Model):
    # stores team_id, booking_time
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer)
    booking_time = db.Column(db.DateTime)
    session_id = db.Column(db.Integer)

    def __init__(self, team_id, booking_time, session_id):
        self.team_id = team_id
        self.booking_time = booking_time
        self.session_id = session_id

    def __repr__(self):
        return "<Booking {0} for team {1} at {2}>".format(self.id, self.team_id, self.booking_time)
    
    def serialize(self):
        # custom serialize datetime object to string
        booking_time = self.booking_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        return {
            "id": self.id,
            "team_id": self.team_id,
            "booking_time": booking_time,
            "session_id": self.session_id
        }
        
@bookings_namespace.route("")
class BookingAdd(Resource):
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
        if not data.get("session_id"):
            return {"success": False, "error": "Missing session_id"}, 400

        parsed_datetime = datetime.strptime(data.get("booking_time"), '%Y-%m-%dT%H:%M:%S.%fZ')

        session_id = data.get("session_id")
        # check if booking already exists
        booking = Booking.query.filter_by(session_id=session_id, booking_time=parsed_datetime).first()
        if booking:
            return {"success": False, "error": "Booking already exists"}, 400
        
        session = Session.query.filter_by(id=session_id).first()
        if not session:
            return {"success": False, "error": "session not found"}, 400
        
        # if admin team (team_id of 25), skip validation
        if data.get("team_id") != 25:

            sessions = Session.query.filter_by(id=session_id).all()
            
            # a team can have a maximum of 4 bookings per session
            bookings = Booking.query.filter_by(team_id=data.get("team_id")).all()
            # filter down the bookings to only the ones found in sessions
            bookings = [b for b in bookings if b.session_id in [bt.id for bt in sessions]]
            
            count = 0
            for b in bookings:
                # check if booking is on the same day
                if b.booking_time.date() == parsed_datetime.date():
                    count += 1
                    print(count, repr(b), parsed_datetime.date())
            if count >= 4:
                return {"success": False, "error": "Your team already has 2 hours worth of bookings for this type of booking"}, 400
        else:
            print("Admin team, skipping validation")

        # create new booking
        booking = Booking(
            team_id=data.get("team_id"),
            booking_time=parsed_datetime,
            session_id=data.get("session_id")
        )

        # add booking to database
        db.session.add(booking)
        db.session.commit()

        return {"success": True, "data": repr(booking)}
    
    # route to delete a booking
    @authed_only
    def delete(self):
        # parses request arguements into data
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        # check for fields
        if not data.get("session_id"):
            return {"success": False, "error": "Missing session_id"}, 400
        if not data.get("booking_time"):
            return {"success": False, "error": "Missing booking_time"}, 400
        
        # get booking from database
        booking = Booking.query.filter_by(session_id=data.get("session_id"), booking_time=data.get("booking_time")).first()

        # if not found, return error
        if not booking:
            return {"success": False, "error": "Booking not found"}, 400

        # delete booking from database
        db.session.delete(booking)
        db.session.commit()

        return {"success": True}
    
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

# route to create new session
@bookings_namespace.route("/session")
class Sessions(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to create a new session.
    This could be for a session for example
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
        if not data.get("session_type"):
            return {"success": False, "error": "Missing session type"}, 400

        # create new session
        session = Session(
            name=data.get("name"),
            description=data.get("description"),
            session_type=data.get("session_type")
        )

        # add session to database
        db.session.add(session)
        db.session.commit()

        return {"success": True, "data": repr(session)}

    # get all sessions
    @authed_only
    def get(self):
        if request.args.get("session_type"):
            # get all sessions nfrom database
            sessions = Session.query.filter_by(session_type=request.args.get("session_type")).all()
            # make sessions serializable
            sessions = [session.serialize() for session in sessions]
            return {"success": True, "data": sessions}
        else:
            # get all sessions from database
            sessions = Session.query.all()
            # make sessions serializable
            sessions = [session.serialize() for session in sessions]
            return {"success": True, "data": sessions}
    
    # delete a session
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

        # get session from database
        session = Session.query.filter_by(id=data.get("id")).first()

        # delete session from database
        db.session.delete(session)
        db.session.commit()

        return {"success": True, "data": repr(session)}
    
    # update a session with put
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
        if not data.get("session_type"):
            return {"success": False, "error": "Missing session type"}, 400

        # get session from database
        session = Session.query.filter_by(id=data.get("id")).first()
        
        # update session
        session.name = data.get("name")
        session.description = data.get("description")
        session.session_type = data.get("session_type")

        # commit changes to database
        db.session.commit()

        return {"success": True, "data": repr(session)}    

# register session/delete to delete all sessions with admin rights
@bookings_namespace.route("/session/delete")
class WorkshopsDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all sessions.
    """

    # user must be admin
    @admins_only
    def delete(self):
        # delete all session from database
        sessions = Session.query.all()
        for session in sessions:
            db.session.delete(session)
        db.session.commit()
        return {"success": True}

# route to create new session type
@bookings_namespace.route("/session_type")
class sessionTypes(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to create a new session type.
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
        if not data.get("start_date"):
            return {"success": False, "error": "Missing start date"}, 400
        if not data.get("end_date"):
            return {"success": False, "error": "Missing end date"}, 400

        # create new session_type
        session_type = SessionType(
            name=data.get("name"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date")
        )

        # add session_type to database
        db.session.add(session_type)
        db.session.commit()

        return {"success": True, "data": repr(session_type)}

    # get all session_types
    @authed_only
    def get(self):
        session_types = SessionType.query.all()
        session_types = [session_type.serialize() for session_type in session_types]
        return {"success": True, "data": session_types}

    # delete a session_type
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

        # get session_type from database
        session_type = SessionType.query.filter_by(id=data.get("id")).first()

        # delete session_type from database
        db.session.delete(session_type)
        db.session.commit()

        return {"success": True, "data": repr(session_type)}
    
    # update a session_type with put
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
        if not data.get("start_date"):
            return {"success": False, "error": "Missing starting date"}, 400
        if not data.get("end_date"):
            return {"success": False, "error": "Missing ending date"}, 400

        # get session_type from database
        session_type = SessionType.query.filter_by(id=data.get("id")).first()
        
        # update session_type
        session_type.name = data.get("name")
        session_type.start_date = data.get("start_date")
        session_type.end_date = data.get("end_date")

        # commit changes to database
        db.session.commit()

        return {"success": True, "data": repr(session_type)}    

# register session_type/delete to delete all session_types with admin rights
@bookings_namespace.route("/session_type/delete")
class WorkshopsDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all session_types.
    """

    # user must be admin
    @admins_only
    def delete(self):
        # delete all session_type from database
        session_types = session_type.query.all()
        for session_type in session_types:
            db.session_type.delete(session_type)
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

    # add admin route
    @app.route("/admin/bookings", methods=['GET'])
    @admins_only
    def admin_bookings_listing():
        return render_template('plugins/bookings/assets/admin.html')
    
    # add admin route to view bookings
    @app.route("/admin/bookings/view", methods=['GET'])
    @admins_only
    def admin_bookings_view_listing():
        return render_template('plugins/bookings/assets/admin_view.html')

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
    @authed_only
    def bookings_view_listing():
        return render_template('plugins/bookings/assets/view.html')