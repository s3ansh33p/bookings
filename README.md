# CTFd Bookings Plugin
Made with ❤︎ by ComSSA for Hackathon - 2023 Singapore and improved for Hackathon - 2024 Perth

Use with the CTFd Framework

## Setup

Install the plugin by cloning the repository into the `CTFd/plugins` directory.
In the admin panel, there will be a plugins dropdown with the bookings plugin listed, click on it to configure the plugin.

You should create an `Admin` team for the plugin. Any user that is added to this team that is not an admin will be given permissions to view team names from bookings.
All admins will be able to view team names from bookings and configure the plugin.

### Options

Schedule Items
```
name: Name of the schedule item
start_date: Start timestamp of the schedule item e.g. 12/07/2024 01:30 PM
end_date: End timestamp of the schedule item e.g. 12/07/2024 05:30 PM
segment: Time slot size selection from 5 minutes to 60 minutes
header: Optional header that will replace session descriptions
```

Sessions
```
name: Name of the session
max_allowed: Maximum number of bookings allowed for the session
description: Optional description of the session
schedule_ids: Checkboxes for the schedule items that the session is available for. E.g. A session runs on a Friday and a Saturday schedule item
```

## 2024 Redesign
This year I didn't have the time contraint of making this 2 days before leaving for singapore, so we did some group brainstorming to improve this plugin.
The diagram below contains our design notes - or open the [BookingSystemDesign.svg](./BookingSystemDesign.svg) file :)

![Plan](./BookingSystemDesign.svg)
