##############################################################################
#
# Copyright (c) 2008-2011 SIA "Alistek". (http://www.alistek.com) All Rights Reserved.
#                    General contacts <info@alistek.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

from barcode import barcode
from openerp.tools import translate
from domain_parser import domain2statement
from currency_to_text import currency_to_text
import base64
import StringIO
from PIL import Image
import time

from openerp.osv import osv
from openerp.modules.registry import RegistryManager

from openerp.report import report_sxw
from openerp.tools.translate import _
from openerp.tools.safe_eval import safe_eval as eval
import re

SVG_PATTERN = re.compile('<svg ([^>]+)>',re.I & re.MULTILINE)
WIDTH_PATTERN = re.compile('width="([0-9A-Za-z]+)',re.I & re.MULTILINE)
HEIGHT_PATTERN = re.compile('height="([0-9A-Za-z]+)',re.I % re.MULTILINE)
FLOAT_PATTERN = re.compile('^[0-9]+(\\.[0-9]*)?$')


class ExtraFunctions(object):
    """ This class contains some extra functions which
        can be called from the report's template.
    """
    def __init__(self, cr, uid, report_id, context):
        self.cr = cr
        self.uid = uid
        self.pool = RegistryManager.get(self.cr.dbname)
        self.report_id = report_id
        self.context = context
        self.functions = {
            'asarray':self._asarray,
            'asimage':self._asimage,
            'html_embed_image':self._embed_image,
            'get_attachments':self._get_attachments,
            'get_name':self._get_name,
            'get_label':self._get_label,
            'getLang':self._get_lang,
            'get_selection_item':self._get_selection_items('item'),
            'safe':self._get_safe,
            'countif':self._countif,
            'count':self._count,
            'sumif':self._sumif,
            'sum':self._sum,
            'max':self._max,
            'min':self._min,
            'average':self._average,
            'large':self._large,
            'small':self._small,
            'count_blank':self._count_blank,
            '_':self._translate_text,
            'gettext':self._translate_text,
            'currency_to_text':self._currency2text(context['company'].currency_id.name), #self._currency2text(context['company'].currency_id.code),
            'barcode':barcode.make_barcode,
            'debugit':self.debugit,
            'dec_to_time':self._dec2time,
            'chunks':self._chunks,
            'browse':self._browse,
            'search':self._search,
            'search_ids':self._search_ids,
            'field_size':self._field_size,
            'field_accuracy':self._field_accuracy,
            'bool_as_icon':self._bool_as_icon,
            'time':time,
            'report_xml': self._get_report_xml(),
            'get_log': self._perm_read(self.cr, self.uid),
            'get_selection_items': self._get_selection_items(),
        }

    def _perm_read(self, cr, uid):
        def get_log(obj, field=None):
            if field:
                return obj.perm_read(self.uid, [obj.id])[0][field]
            else:
                return obj.perm_read(self.uid, [obj.id])[0]
        return get_log

    def _get_report_xml(self):
        return self.pool.get('ir.actions.report.xml').browse(self.cr, self.uid, self.report_id)

    def _get_lang(self, source='current'):
        if source=='current':
            return self.context['lang'] or self.context['user_lang']
        elif source=='company':
            return self.context['user'].company_id.partner_id.lang
        elif source=='user':
            return self.context['user_lang']

    def _bool_as_icon(self, val, kind=0):
        if isinstance(kind, (list, tuple)):
            if val==True:
                return kind [0]
            elif val==False:
                return kind[1]
            else:
                return kind[2]
        bool_kind = {0:{True:self._translate_text('True'), False:self._translate_text('False'), None:""},
                     1:{True:self._translate_text('T'), False:self._translate_text('F'), None:""},
                     2:{True:self._translate_text('Yes'), False:self._translate_text('No'), None:""},
                     3:{True:self._translate_text('Y'), False:self._translate_text('N'), None:""},
                     4:{True:'+', False:'-', None:""},
                     5:{True:'[ + ]', False:'[ - ]', None:"[ ]"},
                     6:{True:'[ x ]', False:'[ ]', None:"[ ]"},
                    }
        return bool_kind.get(kind, {}).get(val, val)

    def _dec2time(self, dec, h_format, min_format):
        if dec==0.0:
            return None
        elif int(dec)==0:
            return min_format.replace('%M', str(int(round((dec-int(dec))*60))))
        elif dec-int(dec)==0.0:
            return h_format.replace('%H', str(int(dec)))
        else:
            return h_format.replace('%H', str(int(dec)))+min_format.replace('%M', str(int(round((dec-int(dec))*60))))

    def _currency2text(self, currency):
        def c_to_text(sum, currency=currency, language=None):
            return unicode(currency_to_text(sum, currency, language or self._get_lang()), "UTF-8")
        return c_to_text

    def _translate_text(self, source):
        trans_obj = self.pool.get('ir.translation')
        trans = trans_obj.search(self.cr,self.uid,[('res_id','=',self.report_id),('type','=','report'),('src','=',source),('lang','=',self.context['lang'] or self.context['user_lang'])])
        if not trans:
            trans_obj.create(self.cr, self.uid, {'src':source,'type':'report','lang':self._get_lang(),'res_id':self.report_id,'name':('ir.actions.report.xml,%s' % source)[:128]})
        return translate(self.cr, False, 'report', self._get_lang(), source) or source

    def _countif(self, attr, domain):
        statement = domain2statement(domain)
        expr = "for o in objects:\n\tif%s:\n\t\tcount+=1" % statement
        localspace = {'objects':attr, 'count':0}
        exec expr in localspace
        return localspace['count']

    def _count_blank(self, attr, field):
        expr = "for o in objects:\n\tif not o.%s:\n\t\tcount+=1" % field
        localspace = {'objects':attr, 'count':0}
        exec expr in localspace
        return localspace['count']

    def _count(self, attr):
        return len(attr)

    def _sumif(self, attr, sum_field, domain):
        statement = domain2statement(domain)
        expr = "for o in objects:\n\tif%s:\n\t\tsumm+=float(o.%s)" % (statement, sum_field)
        localspace = {'objects':attr, 'summ':0}
        exec expr in localspace
        return localspace['summ']

    def _sum(self, attr, sum_field):
        expr = "for o in objects:\n\tsumm+=float(o.%s)" % sum_field
        localspace = {'objects':attr, 'summ':0}
        exec expr in localspace
        return localspace['summ']

    def _max(self, attr, field):
        expr = "for o in objects:\n\tvalue_list.append(o.%s)" % field
        localspace = {'objects':attr, 'value_list':[]}
        exec expr in localspace
        return max(localspace['value_list'])

    def _min(self, attr, field):
        expr = "for o in objects:\n\tvalue_list.append(o.%s)" % field
        localspace = {'objects':attr, 'value_list':[]}
        exec expr in localspace
        return min(localspace['value_list'])

    def _average(self, attr, field):
        expr = "for o in objects:\n\tvalue_list.append(o.%s)" % field
        localspace = {'objects':attr, 'value_list':[]}
        exec expr in localspace
        return float(sum(localspace['value_list']))/float(len(localspace['value_list']))

    def _asarray(self, attr, field):
        expr = "for o in objects:\n\tvalue_list.append(o.%s)" % field
        localspace = {'objects':attr, 'value_list':[]}
        exec expr in localspace
        return localspace['value_list']

    def _get_name(self, obj):
        if obj.__class__==osv.orm.browse_record:
            return self.pool.get(obj._table_name).name_get(self.cr, self.uid, [obj.id], {'lang':self._get_lang()})[0][1]
        return ''

    def _get_label(self, obj, field):
        try:
            if isinstance(obj, report_sxw.browse_record_list):
                obj = obj[0]
            if isinstance(obj, (str,unicode)):
                model = obj
            else:
                model = obj._table_name
            if isinstance(obj, (str,unicode)) or hasattr(obj, field):
                labels = self.pool.get(model).fields_get(self.cr, self.uid, fields=[field], context=self.context)
                return labels[field]['string']
        except Exception, e:
            return ''

    def _field_size(self, obj, field):
        try:
            if isinstance(obj, report_sxw.browse_record_list):
                obj = obj[0]
            if isinstance(obj, (str,unicode)):
                model = obj
            else:
                model = obj._table_name
            if isinstance(obj, (str,unicode)) or hasattr(obj, field):
                size = self.pool.get(model)._columns[field].size
                return size
        except Exception, e:
            return ''

    def _field_accuracy(self, obj, field):
        try:
            if isinstance(obj, report_sxw.browse_record_list):
                obj = obj[0]
            if isinstance(obj, (str,unicode)):
                model = obj
            else:
                model = obj._table_name
            if isinstance(obj, (str,unicode)) or hasattr(obj, field):
                digits = self.pool.get(model)._columns[field].digits
                return digits or [16,2]
        except Exception:
            return []

    def _get_selection_items(self, kind='items'):
        def get_selection_item(obj, field, value=None):
            try:
                if isinstance(obj, report_sxw.browse_record_list):
                    obj = obj[0]
                if isinstance(obj, (str,unicode)):
                    model = obj
                    field_val = value
                else:
                    model = obj._table_name
                    field_val = getattr(obj, field)
                if kind=='item':
                    if field_val:
                        return dict(self.pool.get(model).fields_get(self.cr, self.uid, fields=[field], context=self.context)[field]['selection'])[field_val]
                elif kind=='items':
                    return self.pool.get(model).fields_get(self.cr, self.uid, fields=[field], context=self.context)[field]['selection']
                return ''
            except Exception:
                return ''
        return get_selection_item

    def _get_attachments(self, o, index=None):
        attach_obj = self.pool.get('ir.attachment')
        srch_param = [('res_model','=',o._name),('res_id','=',o.id)]
        if type(index)==str:
            srch_param.append(('name','=',index))
        attachments = attach_obj.search(self.cr,self.uid,srch_param)
        res = [x['datas'] for x in attach_obj.read(self.cr,self.uid,attachments,['datas']) if x['datas']]
        if type(index)==int:
            return res[index]
        return len(res)==1 and res[0] or res
    
    def _asimage(self, field_value, rotate=None, dpi=96.0, width=None, height=None):
        if not field_value:
            return StringIO.StringIO(), 'image/png'
        
        # try to convert params to float               
        if width and isinstance(width,basestring) and FLOAT_PATTERN.match(width):
            width = float(width)
        if height and isinstance(height,basestring) and FLOAT_PATTERN.match(height):
            height = float(height)
        if dpi and isinstance(dpi,basestring) and FLOAT_PATTERN.match(dpi):
            dpi = float(dpi)
        
        # prepare data
        field_value = base64.decodestring(field_value)
        tf = StringIO.StringIO(field_value)
        mimetype = None
        
        # check if it is svg
        if field_value.startswith("<?xml version"):
            svg_header = SVG_PATTERN.finditer(field_value).next()
            if svg_header:
                mimetype = "image/svg+xml"
                svg_header = svg_header.group(1)
                if not width:
                    width = WIDTH_PATTERN.finditer(svg_header).next()
                    if width:
                        width = width.group(1)
                if not height:
                    height = HEIGHT_PATTERN.finditer(svg_header).next()
                    if height:
                        height = height.group(1)
            
        # other image type 
        if not mimetype:            
            tf.seek(0)
            im=Image.open(tf)
            try:
                if rotate!=None:
                    im=im.rotate(int(rotate))
                    tf.seek(0)
                    im.save(tf, im.format.lower())
            except Exception, e:
                pass
        
            im_width = im.size[0]
            im_height = im.size[1]
            mimetype = "image/%s" % im.format.lower()
        
        #size vars
        size_x = None
        size_y = None
        
        # Calc Width
        if width:
            if isinstance(width,basestring):
                size_x = width
            else:
                im_width = width
        if not size_x and im_width:        
            size_x = str(im_width/dpi)+'in'
        
        # Calc Height
        if height:
            if isinstance(height,basestring):
                size_y = height
            else:
                im_height = height
        if not size_y and im_height:
            size_y = str(im_height/dpi)+'in'
        
        # Result
        return tf, mimetype, size_x, size_y

    def _embed_image(self, extention, img, width=0, height=0) :
        "Transform a DB image into an embeded HTML image"
        try:
            if width :
                width = 'width="%spx"'%(width)
            else :
                width = ' '
            if height :
                height = 'width="%spx"'%(height)
            else :
                height = ' '
            toreturn = '<img %s %s src="data:image/%s;base64,%s">' % (width, height, extention, str(img))
            return toreturn
        except Exception, exp:
            print exp
            return 'No image'

    def _large(self, attr, field, n):
        array=self._asarray(attr, field)
        try:
            n-=1
            while(n):
                array.remove(max(array))
                n-=1
            return max(array)
        except ValueError, e:
            return None

    def _small(self, attr, field, n):
        array=self._asarray(attr, field)
        try:
            n-=1
            while(n):
                array.remove(min(array))
                n-=1
            return min(array)
        except ValueError, e:
            return None

    def _chunks(self, l, n):
        """ Yield successive n-sized chunks from l.
        """
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    def _search_ids(self, model, domain):
        obj = self.pool.get(model)
        return obj.search(self.cr, self.uid, domain)

    def _search(self, model, domain):
        obj = self.pool.get(model)
        ids = obj.search(self.cr, self.uid, domain)
        return obj.browse(self.cr, self.uid, ids)

    def _browse(self, *args):
        if not args or (args and not args[0]):
            return None
        if len(args)==1:
            model, id = args[0].split(',')
            id = int(id)
        elif len(args)==2:
            model, id = args
        else:
            raise None
        return self.pool.get(model).browse(self.cr, self.uid, id)

    def _get_safe(self, expression, obj):
        try:
            return eval(expression, {'o':obj})
        except Exception, e:
            return None

    def debugit(self, object):
        """ Run the server from command line and 
            call 'debugit' from the template to inspect variables.
        """
        import pdb;pdb.set_trace()
        return

