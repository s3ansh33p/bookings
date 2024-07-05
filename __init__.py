# create admin route for viewing submitted presentations

from flask import Blueprint, request, render_template # only needed for Blueprint import
from flask_restx import Namespace, Resource
from CTFd.models import db, Teams
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.user import get_current_user_attrs
from CTFd.plugins.migrations import upgrade
from CTFd.api import CTFd_API_v1

from CTFd.plugins import register_plugin_assets_directory

# for datetime parsing
from datetime import datetime

bookings_namespace = Namespace("bookings", description="Endpoint for booking system")

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    segment = db.Column(db.Integer)
    header = db.Column(db.Text)

    def __init__(self, name, start_date, end_date, segment, header):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.segment = segment
        self.header = header

    def __repr__(self):
        return "<Schedule {0} - {1} - {2} - {3} - {4}>".format(self.id, self.name, self.start_date, self.end_date, self.segment)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "segment": self.segment,
            "header": self.header
        }

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    description = db.Column(db.Text)
    max_allowed = db.Column(db.Integer)

    def __init__(self, name, description, max_allowed):
        self.name = name
        self.description = description
        self.max_allowed = max_allowed

    def __repr__(self):
        return "<Session {0} - {1} - {2}>".format(self.id, self.name, self.max_allowed)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "max_allowed": self.max_allowed
        }

class SessionSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer)
    schedule_id = db.Column(db.Integer)

    def __init__(self, session_id, schedule_id):
        self.session_id = session_id
        self.schedule_id = schedule_id

    def __repr__(self):
        return "<SessionSchedule {0} - {1} - {2}>".format(self.id, self.session_id, self.schedule_id)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer)
    booking_time = db.Column(db.DateTime)
    session_id = db.Column(db.Integer)

    def __init__(self, team_id, booking_time, session_id):
        self.team_id = team_id
        self.booking_time = booking_time
        self.session_id = session_id

    def __repr__(self):
        return "<Booking {0} for team {1} at {2} in {3}>".format(self.id, self.team_id, self.booking_time, self.session_id)
    
    def serialize(self):
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
    @authed_only
    def get(self):
        bookings = Booking.query.all()
        bookings = [booking.serialize() for booking in bookings]
        return {"success": True, "data": bookings}
    
    """
	The Purpose of this API Endpoint is to allow a user to add a new booking to the database.
	"""
    @authed_only
    def post(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("team_id"):
            return {"success": False, "error": "Missing team id"}, 400
        if not data.get("booking_time"):
            return {"success": False, "error": "Missing booking time"}, 400
        if not data.get("session_id"):
            return {"success": False, "error": "Missing session id"}, 400

        parsed_datetime = datetime.strptime(data.get("booking_time"), '%Y-%m-%dT%H:%M:%S.%fZ')
        session_id = int(data.get("session_id"))
        
        booking = Booking.query.filter_by(session_id=session_id, booking_time=parsed_datetime).first()
        if booking:
            return {"success": False, "error": "Booking already exists"}, 400
        
        session = Session.query.filter_by(id=session_id).first()
        if not session:
            return {"success": False, "error": "Session not found"}, 400
        
        user = get_current_user_attrs()
        if user.type != "admin" and user.team_id == data.get("team_id"):

            # a team can have a maximum of X bookings per session
            bookings = Booking.query.filter_by(team_id=data.get("team_id")).all()
            # num_bookings_for_session = len([b for b in bookings if b.session_id == session_id])
            num_bookings_for_session = 0
            # only match if on same day
            for b in bookings:
                if b.session_id == session_id and b.booking_time.date() == parsed_datetime.date():
                    num_bookings_for_session += 1
            
            if num_bookings_for_session >= session.max_allowed:
                return {"success": False, "error": "Your team already has the maximum number of bookings for this session on this day"}, 400
            
            # check if booking conflicts with another booking by team
            for b in bookings:
                if b.booking_time == parsed_datetime:
                    return {"success": False, "error": "Booking time conflicts with another booking"}, 400
        elif user.type != "admin":
            return {"success": False, "error": "Unauthorized"}, 400
        else:
            print("Admin user, skipping checks")

        booking = Booking(
            team_id=data.get("team_id"),
            booking_time=parsed_datetime,
            session_id=data.get("session_id")
        )

        db.session.add(booking)
        db.session.commit()

        return {"success": True, "data": repr(booking)}
    
    """
	The Purpose of this API Endpoint is to allow a user to remove a booking.
	"""
    @authed_only
    # [!] Todo check team id matches that of the booking and if admin, bypass
    def delete(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("session_id"):
            return {"success": False, "error": "Missing session id"}, 400
        if not data.get("booking_time"):
            return {"success": False, "error": "Missing booking time"}, 400
        
        booking = Booking.query.filter_by(session_id=data.get("session_id"), booking_time=data.get("booking_time")).first()

        if not booking:
            return {"success": False, "error": "Booking not found"}, 400
        
        user = get_current_user_attrs()
        if user.team_id == booking.team_id or user.type == "admin":
            db.session.delete(booking)
            db.session.commit()
        else:
            return {"success": False, "error": "Unauthorized"}, 400

        return {"success": True}
    
@bookings_namespace.route("/delete")
class BookingDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all bookings.
    """
    @admins_only
    def delete(self):
        bookings = Booking.query.all()
        for booking in bookings:
            db.session.delete(booking)
        db.session.commit()
        return {"success": True}

@bookings_namespace.route("/session")
class Sessions(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to create a new session.
    """
    @admins_only
    def post(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("name"):
            return {"success": False, "error": "Missing name"}, 400
        if not data.get("max_allowed"):
            return {"success": False, "error": "Missing max allowed"}, 400
        if not data.get("schedule_ids"):
            return {"success": False, "error": "Missing schedule ids"}, 400

        session = Session(
            name=data.get("name"),
            max_allowed=data.get("max_allowed"),
            description=data.get("description") if data.get("description") else ""
        )
        db.session.add(session)
        db.session.commit()
        
        session_schedule = []
        for schedule_id in data.get("schedule_ids"):
            session_schedule.append(SessionSchedule(
                session_id=session.id,
                schedule_id=schedule_id
            ))

        db.session.add_all(session_schedule)
        db.session.commit()

        return {"success": True, "data": repr(session)}

    """
    The Purpose of this API Endpoint is to allow a user to view sessions.
    """
    @authed_only
    def get(self):
        if request.args.get("schedule_id"):
            # Get session ids from SessionSchedule, then get those matching sessions
            session_schedules = SessionSchedule.query.filter_by(schedule_id=request.args.get("schedule_id")).all()
            sessions = Session.query.filter(Session.id.in_([ss.session_id for ss in session_schedules])).all()
            sessions = [session.serialize() for session in sessions]
            return {"success": True, "data": sessions}
        else:
            # Otherwise, get all sessions
            sessions = [session.serialize() for session in Session.query.all()]
            for session in sessions:
                session["schedule_ids"] = []
            
            session_schedules = SessionSchedule.query.order_by(SessionSchedule.session_id).all()
            schedule_counter = 0
            session_counter = 0
            while schedule_counter < len(session_schedules):
                found = False
                while not found:
                    if sessions[session_counter]["id"] != session_schedules[schedule_counter].session_id:
                        session_counter += 1
                    else:
                        found = True
                sessions[session_counter]["schedule_ids"].append(session_schedules[schedule_counter].schedule_id)
                schedule_counter += 1

            return {"success": True, "data": sessions}
    
    """
    The Purpose of this API Endpoint is to allow an admin to delete a session.
    """
    @admins_only
    def delete(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("id"):
            return {"success": False, "error": "Missing id"}, 400

        session = Session.query.filter_by(id=data.get("id")).first()

        db.session.delete(session)

        # remove all session schedules
        existing_session_schedule = SessionSchedule.query.filter_by(session_id=session.id).all()
        for ess in existing_session_schedule:
            db.session.delete(ess)

        db.session.commit()

        return {"success": True, "data": repr(session)}
    
    """
    The Purpose of this API Endpoint is to allow an admin to update a session.
    """
    @admins_only
    def put(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("id"):
            return {"success": False, "error": "Missing id"}, 400
        if not data.get("name"):
            return {"success": False, "error": "Missing name"}, 400
        if not data.get("max_allowed"):
            return {"success": False, "error": "Missing max allowed"}, 400
        if not data.get("schedule_ids"):
            return {"success": False, "error": "Missing schedule ids"}, 400 

        session = Session.query.filter_by(id=data.get("id")).first()

        existing_session_schedule = SessionSchedule.query.filter_by(session_id=session.id).all()
        for ess in existing_session_schedule:
            db.session.delete(ess)

        session_schedule = []
        for schedule_id in data.get("schedule_ids"):
            session_schedule.append(SessionSchedule(
                session_id=session.id,
                schedule_id=schedule_id
            ))

        db.session.add_all(session_schedule)

        session.name = data.get("name")
        session.description = data.get("description") if data.get("description") else ""
        session.max_allowed = data.get("max_allowed")

        db.session.commit()

        return {"success": True, "data": repr(session)}    

@bookings_namespace.route("/session/delete")
class WorkshopsDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all sessions.
    """
    @admins_only
    def delete(self):
        sessions = Session.query.all()
        for session in sessions:
            db.session.delete(session)
        
        session_schedules = SessionSchedule.query.all()
        for session_schedule in session_schedules:
            db.session.delete(session_schedule)

        db.session.commit()
        return {"success": True}

@bookings_namespace.route("/schedule")
class Schedules(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to create a new schedule item.
    """
    @admins_only
    def post(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("name"):
            return {"success": False, "error": "Missing name"}, 400
        if not data.get("start_date"):
            return {"success": False, "error": "Missing start date"}, 400
        if not data.get("end_date"):
            return {"success": False, "error": "Missing end date"}, 400
        if not data.get("segment"):
            return {"success": False, "error": "Missing segment"}, 400

        schedule_item = Schedule(
            name=data.get("name"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            segment=data.get("segment"),
            header=data.get("header") if data.get("header") else ""
        )

        db.session.add(schedule_item)
        db.session.commit()

        return {"success": True, "data": repr(schedule_item)}

    """
    The Purpose of this API Endpoint is to get schedule items.
    """
    @authed_only
    def get(self):
        items = Schedule.query.all()
        items = [item.serialize() for item in items]
        return {"success": True, "data": items}

    """
    The Purpose of this API Endpoint is to allow an admin to delete a schedule item.
    """
    @admins_only
    def delete(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("id"):
            return {"success": False, "error": "Missing id"}, 400

        item = Schedule.query.filter_by(id=data.get("id")).first()

        session_schedule = SessionSchedule.query.filter_by(schedule_id=item.id).all()
        for ss in session_schedule:
            db.session.delete(ss)

        db.session.delete(item)
        db.session.commit()

        return {"success": True, "data": repr(item)}
    
    """
    The Purpose of this API Endpoint is to allow an admin to update a schedule item.
    """
    @admins_only
    def put(self):
        if request.content_type != "application/json":
            data = request.form
        else:
            data = request.get_json()

        if not data.get("id"):
            return {"success": False, "error": "Missing id"}, 400
        if not data.get("name"):
            return {"success": False, "error": "Missing name"}, 400
        if not data.get("start_date"):
            return {"success": False, "error": "Missing start date"}, 400
        if not data.get("end_date"):
            return {"success": False, "error": "Missing end date"}, 400
        if not data.get("segment"):
            return {"success": False, "error": "Missing segment"}, 400

        item = Schedule.query.filter_by(id=data.get("id")).first()

        item.name = data.get("name")
        item.start_date = data.get("start_date")
        item.end_date = data.get("end_date")
        item.segment = data.get("segment")
        item.header = data.get("header") if data.get("header") else ""
        
        db.session.commit()

        return {"success": True, "data": repr(item)}    

@bookings_namespace.route("/schedule/delete")
class WorkshopsDelete(Resource):
    """
    The Purpose of this API Endpoint is to allow an admin to delete all schedule items.
    """

    @admins_only
    def delete(self):
        items = Schedule.query.all()
        for item in items:
            db.session.delete(item)

        session_schedule = SessionSchedule.query.all()
        for ss in session_schedule:
            db.session.delete(ss)
            
        db.session.commit()
        return {"success": True}

@bookings_namespace.route("/teams")
class BookingTeams(Resource):
    """
    The Purpose of this API Endpoint is to allow a user to view all teams.
    """

    @authed_only
    def get(self):
        teams = Teams.query.all()
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