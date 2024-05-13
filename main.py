import flask, flask_discord, os, urllib.request, pymongo, re, datetime, emoji, dotenv
from flask import request, render_template, redirect, url_for, abort, flash
from markupsafe import Markup
from classes import conf, cmds

dotenv.load_dotenv()

app = flask.Flask("dashboard")
app.secret_key=os.environ["app_secret_key"]
app.config["DISCORD_CLIENT_SECRET"] = os.environ["DISCORD_CLIENT_SECRET"]
app.config["DISCORD_BOT_TOKEN"] = os.environ["DISCORD_BOT_TOKEN"]
app.config["DISCORD_CLIENT_ID"] = 439166087498825728
app.config["DISCORD_REDIRECT_URI"] = "https://bot.elisttm.space/callback"
discord = flask_discord.DiscordOAuth2Session(app)

db = pymongo.MongoClient(os.environ["mongo"])['trashbot']

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"

def get_url(url:str):
	return urllib.request.urlopen(url).read().decode('utf8')

# this function sucks really really bad i hate you 2021 eli
def get_db(db, id, p=None, d=None):
	projection = {'_id':0}
	if p is not None:
		for _p_ in [p] if not isinstance(p, list) else p:
			projection[_p_] = 1
	data = db.find_one({'_id':id},projection)
	if not data:
		return d
	return data

def fetch_user(discord):
	return discord.fetch_user() if discord.authorized else None

def md(text, urls=False):
	if urls:
		for x in re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text):
			text = text.replace(x, f'<a href="{x}">{x}</a>')
	for x in re.findall(r'\[(img|video|audio|iframe):(.*?)\]', text):
		if x[0] == 'video' or x[0] == 'audio':
			replacement = f'<{x[0]} controls><source src="{x[1]}" type="{(x[1].rsplit(".", 1))[1]}"></{x[0]}>'
		elif x[0] == 'img':
			replacement = f'<img src="{x[1]}"/>'
		elif x[0] == 'iframe':
			replacement = f'<iframe src="{x[1]}" frameborder="0"></iframe>'
		text = text.replace(f'[{x[0]}:{x[1]}]', replacement)
	for x in re.findall(r'\[(a|c|style):(.*?):(.*?)\]', text):
		if x[0] == 'a':
			replacement = f'<a href="{x[1]}">{x[2]}</a>'
		elif x[0] == 'c':
			replacement = f'<span style="color:{x[1]}">{x[2]}</span>'
		elif x[0] == 'style':
			replacement = f'<span style="{x[1]}">{x[2]}</span>'
		text = text.replace(f'[{x[0]}:{x[1]}:{x[2]}]', replacement)
	for x in re.findall(r'\[(h2|h3|b|i|u|s|sup|sub):(.*?)\]', text):
		text = text.replace(f'[{x[0]}:{x[1]}]', f'<{x[0]}>{x[1]}</{x[0]}>')
	for x in re.findall(r'\[(br|h1)\]', text):
		text = text.replace(f'[{x[0]}]', f'<{x[0]}>')
	return Markup(text)

##################################################

@app.route("/login")
def login():
	return discord.create_session(scope=["identify", "guilds"])

@app.route("/logout/")
def logout():
	discord.revoke()
	return redirect(url_for("commands"))

@app.route("/callback/")
def callback():
	try:
		discord.callback()
	except Exception as e:
		print(e)
	finally:
		return redirect(url_for("authorize"))
	
@app.route("/authorize")
@flask_discord.requires_authorization
def authorize():
	user = discord.fetch_user()
	return redirect(url_for("commands"))

@app.errorhandler(flask_discord.Unauthorized)
def redirect_unauthorized(e):
	flash('failed to authenticate!')
	return redirect(url_for("commands"))

##################################################

@app.route('/')
@app.route('/commands')
def commands():
	return render_template('helplist.html', cmds = cmds.cmds, md=md, user=fetch_user(discord))

class tag_funcs:
	def timeform(tagdate):
		return datetime.datetime.utcfromtimestamp(tagdate).strftime('%-m/%-d/%y @ %I:%M%P')

	def cparse(text):
		for x in re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text):
			text = text.replace(x, f'<a href="{x}">{x}</a>')
		return Markup(text)

@app.route('/tags', defaults={'search': None})
@app.route('/tags/', defaults={'search': None})
@app.route('/tags/<int:search>')
def tags(search):
	tags_list = list(db['tags'].find({} if not search else {'owner':search}).sort('date',-1))
	return render_template('tags.html', tags_list=tags_list, search=search, tagf=tag_funcs, header=f"all tags owned by ID {search}" if search else "list of all public tags", user=fetch_user(discord))

@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(500)
def error_handlers(error):
	return render_template('errors.html', errors={
			403: ["[403] forbidden","you do not have permission to access this content. usually this is because you dont have admin in a server"],
			404: ["[404] page not found","the url youre trying to access does not exist, you probably put the link in wrong or i just messed something up"],
			500: ["[500] internal server error","somewhere along the way there was an error processing your request; if this keeps happening, please get in contact",],
		}, error=error), error.code
	
##################################################

@app.route('/servers')
@flask_discord.requires_authorization
def servers():
	user = discord.fetch_user()
	bot_guilds = get_db(db['misc'], 'misc', 'guilds')['guilds']
	guilds = [guild for guild in discord.fetch_guilds() if guild.permissions.administrator and guild.id in bot_guilds]
	return render_template('guilds.html', guilds=guilds, user=user)

@app.route('/config/<int:guild_id>', methods=['GET', 'POST'])
@flask_discord.requires_authorization
def config(guild_id):
	user = discord.fetch_user()
	guilds = discord.fetch_guilds()
	for x in guilds:
		if x.id == guild_id:
			guild = x
			break
	try:
		if not guild or not guild.permissions.administrator and user.id != 216635587837296651:
			return abort(403)
		bot_guild = discord.bot_request(f'/guilds/{guild_id}')
		if 'id' not in bot_guild:
			return abort(403)
		guild_channels = discord.bot_request(f'/guilds/{guild_id}/channels')
	except flask_discord.exceptions.RateLimited:
		return abort(429)
	guild.roles = [role for role in bot_guild['roles'] if not role['managed'] and role['name'] != '@everyone']
	guild.channels = [channel for channel in guild_channels if channel['type'] == 0]
	
	if request.method == 'POST':
		guild_data = get_db(db['config'], guild_id, d={})
		apply_data = {"$set":{},}
		form = dict(((request.form).lists()))
		if form['submit'] == ['reset']:
			db['config'].remove({'_id':guild_id})
			flash('successfully reset configuration file!')
			return redirect(url_for('config', guild_id=guild_id))
		for key in conf.keys:
			if key not in form:
				if conf.keys[key]['type'] == 'list':
					form[key] = None
				else:
					continue
			value = form[key][0] if conf.keys[key]['type'] != 'list' else form[key]
			if conf.keys[key]['type'] == 'toggle':
				value = True if value == 'enabled' else False
			if (conf.keys[key]['type'] == 'number' or conf.keys[key]['type'] == 'role' or conf.keys[key]['type'] == 'channel') and value != '':
				value = int(value)
			if conf.keys[key]['type'] == 'emoji':
				if value not in emoji.UNICODE_EMOJI['en']:
					try:
						value = int(value)
					except:
						pass
					if not isinstance(value, int) or len(str(value)) != 18:
						flash(f'invalid entry for {key}, must be custom emoji ID or unicode emoji!')
						continue
			if key in guild_data and guild_data[key] == value:
				continue
			if value == '' or value is None or ('default' in conf.keys[key] and value == conf.keys[key]['default']):
				if key in guild_data:
					if '$unset' not in apply_data:
						apply_data['$unset'] = {key:0}
					else:
						apply_data['$unset'][key] = 0
				continue
			apply_data['$set'][key] = value
		if len(apply_data['$set']) == 0:
			del apply_data['$set']
		if len(apply_data) != 0:
			db['config'].update_one({'_id':guild_id}, apply_data, upsert=True)
			flash('successfully applied changes!')
		return redirect(url_for('config', guild_id=guild_id))
	guild_data = get_db(db['config'], guild_id, d={})
	for key in conf.keys:
		if key not in guild_data and 'default' in conf.keys[key]:
			guild_data[key] = conf.keys[key]['default']
	return render_template('config.html', guild_data=guild_data, conf=conf, guild=guild, user=user)


##################################################

if __name__ == '__main__':
	app.run(host="0.0.0.0", port=7576, use_reloader=False)
