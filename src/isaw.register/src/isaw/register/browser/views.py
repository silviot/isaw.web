# This needs a lot of work and unit testing for failures
# As failure occurs, and it will, especially with the printer routine below
# a test should be added - christopher.warner@nyu.edu
import random

from zope.interface import Interface
from zope import schema
from zope.component import getUtility
from zope.formlib import form
from five.formlib import formbase

from Acquisition import aq_inner
from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName
from Products.CMFDefault.exceptions import EmailAddressInvalid
from Products.Five.browser import BrowserView

from Products.CMFPlone import PloneMessageFactory as _
from Products.statusmessages.interfaces import IStatusMessage

from plone import api

from smtplib import SMTPRecipientsRefused


def checkEmailAddress(value):
    portal = getUtility(ISiteRoot)
    reg_tool = getToolByName(portal, 'portal_registration')
    if value and reg_tool.isValidEmail(value):
        pass
    else:
        raise EmailAddressInvalid
    return True


class ISiteWideUserForm(Interface):

    fullname = schema.TextLine(
        title=u"Fullname",
        description=u"Enter full name, e.g. John Smith.",
        required=True
    )

    email = schema.ASCIILine(
        title=u"Email",
        description=u"Enter an email address. This resembles netid@nyu.edu",
        required=True,
        constraint=checkEmailAddress
    )


class SiteWideUserForm(formbase.PageForm):
    form_fields = form.FormFields(ISiteWideUserForm)

    label = (u"Add a new sitewide user (website, copiers, ticket system)")
    description = (u"Onboard a new sitewide user to all ISAW systems")

    @form.action(u"Add new user")
    def action_send(self, action, data):
        """ Add's new user and then an email is sent """
        context = aq_inner(self.context)
        urltool = getToolByName(context, 'portal_url')
        portal = urltool.getPortalObject()

        userid = data['fullname']
        uemail = data['email']
        netid = uemail.partition("@")
        netid = netid[0]
        ucode = random.randint(10000, 99999)

        ###################
        # Plone user create

        plone_props = dict(
            fullname=userid,
        )

        api.user.create(
            username=uemail,
            email=uemail,
            properties=plone_props
        )

        ucode = ucode + 50

        email_charset = getattr(self, 'email_charset', 'UTF-8')

        email = portal.sitewide_user_email
        mail_text = email(charset=email_charset, request=context.REQUEST,
                          emailto=uemail, fullname=userid, usercode=ucode,
                          netid=netid)
        try:
            maildaemon = getToolByName(self, 'MailHost')
            return maildaemon.send(
                mail_text, mto=uemail,
                mfrom="isaw.it-group@nyu.edu",
                subject="ISAW User Code and Help Information",
                encode='text/plain',
                immediate=True
            )

        except SMTPRecipientsRefused:
            raise SMTPRecipientsRefused('Recipient address rejected')

        self.request.response.redirect(
            portal.absolute_url() + '/@@sitewide_user'
        )
        IStatusMessage(self.request).addStatusMessage(
            _(u"Sitewide user " + userid + " added."), type=u'info'
        )

        return


class SiteWideUser(BrowserView):
    pass
