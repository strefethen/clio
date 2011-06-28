import datetime
import os

from django.utils import simplejson
from google.appengine.api import channel
from google.appengine.api import prospective_search
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from config import config
import model


class IndexHandler(webapp.RequestHandler):
  """Serve up the Clio admin interface."""

  def get(self):
    client_id = os.urandom(16).encode('hex')
    channel_key = channel.create_channel(client_id)
    template_path = os.path.join(os.path.dirname(__file__),
                                 'templates', 'index.html')
    self.response.out.write(template.render(template_path, {
        'config': config,
        'client_id': client_id,
        'channel_key': channel_key,
    }))


class SubscribeHandler(webapp.RequestHandler):
  """Handle subscription requests from clients."""

  def post(self):
    sub = model.Subscription(
        client_id=self.request.POST['client_id'],
        expires=datetime.datetime.now() + config.SUBSCRIPTION_TIMEOUT)
    sub.put()
    prospective_search.subscribe(
        model.RequestRecord,
        self.request.POST['query'],
        str(sub.key()))
    self.response.out.write(str(sub.key()))


class MatchHandler(webapp.RequestHandler):
  """Process matching log entries and send them to clients."""

  def post(self):
    # Fetch the log record
    record = prospective_search.get_document(self.request)
    record_data = record.to_json()

    # Fetch the set of subscribers to send this record to
    subscriber_keys = map(db.Key, self.request.get_all('id'))
    subscribers = db.get(subscriber_ids)

    for subscriber in subscribers:
      # If the subscription has expired, delete it
      if subscriber.expires < datetime.datetime.now():
        prospective_search.unsubscribe(model.RequestRecord, subscriber.key())
        subscriber.delete()
      else:
        data = simplejson.dumps({
            'subscription_key': subscriber.key(),
            'data': record_data,
        })
        channel.send_message(subscriber.client_id, data)


application = webapp.WSGIApplication([
    (config.BASE_URL + '/', IndexHandler),
    (config.BASE_URL + '/subscribe', SubscribeHandler),
    (config.QUEUE_URL, MatchHandler),
])


def main():
  run_wsgi_app(application)


if __name__ == "__main__":
  main()
