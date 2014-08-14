''' migrate all UserVoice tickets to Zendesk using official APIs from Uservoice'''
''' to do: refactor for clarity, add user import, and fix multi-comment threads, which aren't working'''

import json
import requests
from uservoice_config import *
from zendesk_config import *

def reformat_uv_messages(new_ticket, uv_messages):
	'''input is a list of nested dicts. See data_types.md for full description, since 
	UserVoice doesn't have one.

	['body', 
	'attachments',
	'channel',
	'created_at', 
	'updated_at', 
	'is_admin_response', 
	'id', 
	'plaintext_body', 
	'sender']

	output should look like:
	"comments": [
	      { "author_id": 827, "value": "This is a comment", "created_at": "2009-06-25T10:15:18Z" },
	      { "author_id": 19, "value": "This is a private comment", "public": false }
	    ]
	'''
	comments = []
	dates = []
	is_first_message = True
	for message in uv_messages:
		dates.append(message['created_at'])		
		if is_first_message:
			new_ticket['description'] = message['body']
			new_ticket['created_at'] = message['created_at']
			is_first_message = False
		else:
			zd_message = {}
			zd_message['updated_at'] = message['updated_at']
			zd_message['author_id'] = 352695485
			zd_message['value'] = message['body']
			comments.append(zd_message)
		''' 
		it turns out that a user must already exist to be an author
		so, I created a user to hold all old tickets, with id = 352590805
		'''
		
	dates.sort()
	#add a try catch to get tickets with no messages
	try:
		new_ticket['created_at'] = dates[0] #min of messages
		new_ticket['updated_at'] = dates[-1] #max of messages
		new_ticket['solved_at'] = dates[-1]
	except IndexError:
		new_ticket['created_at'] = message['created_at'] #min of messages
		new_ticket['solved_at'] = message['created_at']
	except:
		pass
		
	new_ticket['comments'] = comments
	new_ticket['requester_id'] = 352695485
	new_ticket['submitter_id'] = 352695485

	''' to do: create users and add to a userlist to map uservoice id to zendesk_id'''

	return new_ticket

def get_tags(ticket_custom_fields):
	'''takes a list of dicts of UV custom fields and creates zd tags'''
	tags = []
	for field in ticket_custom_fields:
		tag = field['value']
		if tag != u"N/A" and tag != u'Support Request':
			#Zendesk tickets do not support spaces; let's make lowercase too
			tag = tag.replace(" ", "-").lower()
			tags.append(tag)
	tags.append("imported")			
	return tags

def create_uv_client():
	'''returns a uservoice client api instance'''
	import uservoice
	
	
	return uservoice.Client(SUBDOMAIN_NAME, API_KEY, API_SECRET)

def send_ticket_to_zd(new_ticket):
	_url = "https://%s.zendesk.com/api/v2/imports/tickets.json" % subdomain
	_headers = {'Content-Type': 'application/json'}
	_data = json.dumps({'ticket': new_ticket})

	r = requests.post(_url, data = _data, auth=(email, zendesk_password), headers=_headers)
	if r.status_code != 201:
		with open("errorfile.log", "a") as errorfile:
			errorfile.write(str(new_ticket['external_id'])+"\n")
			errorfile.write(str(r.status_code)+"\n")
			errorfile.write(_data)
			errorfile.write("\n")
			print r.text
	else:
		with open("successes.log", "a") as successes:
			successes.write(_data)
			successes.write("\n")
	# you can also curl if you prefer!
	#from os import system
	#command = '''curl "https://%s.zendesk.com/api/v2/imports/tickets.json" -v -u %s:%s -X POST -d "%s" -H "Content-Type: application/json"''' % (subdomain, email, zendesk_password, data)
	#print command
	#system(command)
	
def download_uv_tickets(uv_ticket_outfile, total_records):
	'''hits the uservoice API to return tickets 100 at a time'''
	uv_client = create_uv_client()
	base_url = "/api/v1/tickets.json?"
	total_records = total_records
	
	tickets = {}
	page = 1
	print "Downloading page %s" % str(page)
	with open(outfile, "w") as f:
		while total_records > page*100:
			request = base_url+"page="+str(page)+"&per_page=100"+"&type=Support+Request"
			response = uv_client.get(request)
			f.write(json.dumps(response['tickets'])+"\n")
			print json.dumps(response['response_data'])
			page = response['response_data']['page'] + 1 
			total_records = response['response_data']['total_records']
			print "Downloading page %s of %s pages" % (str(page), str(total_records/100))

def print_uv_ticket_structure(ticket):
	'''this was just used for testing'''
	print ticket.keys()
	for key in ticket.keys():
		print key 
		print type(ticket[key])
		if type(ticket[key]) == dict:
			print ticket[key].keys()
		if type(ticket[key]) == list: 
			try:
				print ticket[key][0].keys()
			except:
				print ticket[key]

def import_tickets_to_zd(uv_ticket_outfile):
	''' read through uservoice export file in batches '''
	with open("uservoice_export.json", "r") as uservoice_export:
		batch = 1
		for line in uservoice_export: 
			print "Working on ticket batch %i" % batch
			ticket_batch = json.loads(line)
			for ticket in ticket_batch:			
				new_ticket = process_uv_ticket(ticket)
				send_ticket_to_zd(new_ticket)
			batch += 1

def process_uv_ticket(ticket): 		
	''' API format http://developer.zendesk.com/documentation/rest_api/tickets.html'''
	''' to do: make more mappings;  make them better; import users and orgs '''
	#map to the UV id. Can we force an ID in zendesk to match?
	new_ticket = {}
	new_ticket = reformat_uv_messages(new_ticket, ticket['messages'])
	new_ticket['external_id'] = int(ticket['url'].split("/")[-1])
	new_ticket['subject'] = ticket['subject']
	new_ticket['tag'] = get_tags(ticket['custom_fields'])
	try: 
		new_ticket['assignee_id'] = ticket['assignee']['id']
	except KeyError:
		#new_ticket['assignee_id'] = None
		pass
	# add static values to all tickets? include channel
	new_ticket['status'] = 'closed'
	new_ticket['recipient'] = 'support@mixpanel.com'
	return new_ticket
	
if __name__ == '__main__':
	uv_ticket_outfile = "uservoice_export.json"
	#note; I don't really want to get all the UV tickets right now.
	''' to do: make each API call write to Zendesk without using disk '''
	if False:
		download_uv_tickets(uv_ticket_outfile, total_records=60000)
		print "not really downloading ticket"
	import_tickets_to_zd(uv_ticket_outfile)
