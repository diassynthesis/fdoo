# -*- coding: utf-8 -*-
import logging

from openerp import http
from openerp.http import request
from openerp.addons.web.controllers.main import login_redirect

_logger = logging.getLogger(__name__)


class PosController(http.Controller):

    @http.route('/pos/web', type='http', auth='user')
    def a(self, debug=False, **k):
        cr, uid, context, session = request.cr, request.uid, request.context, request.session

        if not session.uid:
            return login_redirect()

        PosSession = request.registry['pos.session']
        pos_session_ids = PosSession.search(cr, uid, [('state','=','opened'),('user_id','=',session.uid)], context=context)
        PosSession.login(cr,uid,pos_session_ids,context=context)
        
        modules =  simplejson.dumps(module_boot(request.db))
        init =  """
                 var wc = new s.web.WebClient();
                 wc.show_application = function(){
                     wc.action_manager.do_action("pos.ui");
                 };
                 wc.setElement($(document.body));
                 wc.start();
                 """

        html = request.registry.get('ir.ui.view').render(cr, session.uid,'point_of_sale.index',{
            'modules': modules,
            'init': init,
        })

        return html
