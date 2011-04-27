from bytecode import disassemble # for verbosity

def extractTypes(string):
    res = []
    strtype = ''
    while len(string) > 0:
        if string[0] == 'B':
            strtype += 'boolean'
            size = 1
        elif string[0] == 'I':
            strtype += 'integer'
            size = 1
        elif string[0] == 'S':
            strtype += 'short'
            size = 1
        elif string[0] == 'Z':
            string = string[1:]
            end = string.find(';')
            strtype += 'ref of '+string[:end - 1]
            size = end
        elif string[0] == 'V':
            strtype += 'void'
            size = 1
        elif string[0] == '[':
            strtype = 'array of '
            string = string[1:]
            continue
        else:
            assert False, string[0]+' not recognized'
        res.append(strtype)
        string = string[size:]
    return res

class ExceptionHandler(object):
    def __init__(self, orig_offset, handler_info, cap_file, resolver):
        """ handler is the type found in the cap_file """
        print orig_offset, handler_info.handler_offset, handler_info.start_offset
        self.handler_offs = handler_info.handler_offset - orig_offset
        self.start = handler_info.start_offset - orig_offset
        self.stop = self.start + handler_info.active_length
        self.last = bool(handler_info.stop_bit)
        catch_type_offs = handler_info.catch_type_index
        self.isFinally = False
        if catch_type_offs == 0:
            self.isFinally = True
        else:
            self.catch_type = resolver.resolveIndex(
                catch_type_offs, cap_file)

    def __contains__(self, ip):
        """ returns if the ip is in the range of this handler """
        print self.start, ip, self.stop
        return self.start < ip < self.stop
    
    def match(self, exception):
        if self.isFinally:
            return True
        print self.catch_type.cls
        res = isinstance(exception, self.catch_type.cls)
        return res

class JavaCardMethod(object):
    def _fillHandlers(self, cap_file, resolver):
        # We now care about the exception handlers
        bytecode_orig = self.offset + self.method_info.method_info.size
        mdi = self.method_descriptor_info
        self.excpt_handlers = []
        for hdlr in xrange(mdi.exception_handler_index, 
                           mdi.exception_handler_index + 
                           mdi.exception_handler_count):
            self.excpt_handlers.append(ExceptionHandler(
                    bytecode_orig, cap_file.Method.exception_handlers[hdlr], cap_file, resolver))

class JavaCardStaticMethod(JavaCardMethod):
    """
    The goal of this class is to make things easier for the JavaCardFrame
    This class would embed the parameters, the bytecode and the exception 
    handlers (more might come later)
    """
    def __init__(self, offset, cap_file, resolver):
        """ 
        This object is first created from information of the export_file and 
        the ConstantPool. Those only provide the offset in the Method 
        Component in case of internal references.
        """
        self.offset = offset
        self._feedFromCAP(cap_file, resolver)

    def _feedFromCAP(self, cap_file, resolver):
        """ 
        We init it from components of the cap_file
        """
        # Get the methodInfo is not too complicated
        self.method_info = cap_file.Method.methods[self.offset]
        # Now, we also'd like the MethodDescriptorInfo
        self.method_descriptor_info = None
        for cls in cap_file.Descriptor.classes:
            for mtd in cls.methods:
                if mtd.method_offset == self.offset:
                    # Bingo !
                    self.method_descriptor_info = mtd
                    break
        assert self.method_descriptor_info is not None, "Method Not found in Descriptor Component"
        # We now care about the exception handlers
        self._fillHandlers(cap_file, resolver)
        # I first want the number of arguments
        self.nargs = self.method_info.method_info.nargs
        self.bytecodes = self.method_info.bytecodes

    def __str__(self):
       return "<JavaCardStaticMethod %d args, %d excpt handlers, %s>" % (
           self.nargs,
           len(self.excpt_handlers),
           ', '.join(disassemble(self.methodinfo.bytecodes)),
           )

class PythonStaticMethod(object):
    """
    This is the Python version of the JavaCardMethod
    We need to know the parameters, their number and types
    We also need to know if the function returns something
    """
    def __init__(self, name, typ, method):
        self.name = name
        self.type = typ
        self.method = method
        self._analyseType(typ)

    def _analyseType(self, string):
        assert string[0] == '('
        # First analyse the params
        self.params = extractTypes(string[1:string.find(')')])
        self.retType = extractTypes(string[string.find(')') + 1:])[0]

    def __call__(self, *params):
        return self.method(*params)

    def __str__(self):
        return "<PythonStaticMethod %d args, %s, %s>" % (
           len(self.params), self.retType, self.method.__name__
           )

class JavaCardVirtualMethod(JavaCardMethod):
    def __init__(self, clsoffset, token, cap_file, resolver):
        self.token = token
        self._feedFromCAP(clsoffset, cap_file, resolver)

    def _feedFromCAP(self, clsoffset, cap_file, resolver):
        """ actually, we are only interested in the nember of parameters """
        class_info = cap_file.Class.classes[clsoffset]
        cdi = None
        mdi = None
        for cls in cap_file.Descriptor.classes:
            if cls.this_class_ref.class_ref == clsoffset:
                cdi = cls
                for mtd in cdi.methods:
                    if mtd.token == self.token:
                        mdi = mtd
                        break
                break
        assert cdi
        assert mdi
        self.method_descriptor_info = mdi
        self.offset = mdi.method_offset
        self.method_info = cap_file.Method.methods[self.offset]
        self._fillHandlers(cap_file, resolver)
        self.nargs = self.method_info.method_info.nargs
        self.bytecodes = self.method_info.bytecodes

class PythonVirtualMethod(object):
    """
    This object has to be initialised twice, once with the infos, and a second
    time with the actual object refereference
    """
    def __init__(self, name, typ):
        self.name = name
        self._analyseType(typ)
        self.method = None

    def _analyseType(self, string):
        assert string[0] == '('
        # First analyse the params
        self.params = extractTypes(string[1:string.find(')')])
        self.retType = extractTypes(string[string.find(')') + 1:])[0]

    def bindToObject(self, obj):
        self.method = getattr(obj, self.name)

    def __call__(self, *params):
        assert self.method
        return self.method(*params)
