# -*- coding: utf-8 -*-
import re, os

class StringFormatting(object):
    """ The goal here is to have one formatting string that can cope with any
        type of release.  We don't want different strings for Various Artists,
        or multidisc releases, where each disc has a separate title.

        One string to rule them all.

        Some string formatting functions. Loosely based on:
        http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference

        Limitations:
            don't leave empty conditions (or potentiall empty), blank
            placeholders.

            $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ') -- good
            $if1($strcmp(%artist%,%albumartist%),,%artist% - ) -- bad

        Example:
        stringFormatting = StringFormatting()
        stringFormatting.test()

        string = "%albumartist%/[%year%] %album%/$num(%track%,2) $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ')%title%%fileext%"
        new_string = stringFormatting.parseString(string)

        See tests for more examples
    """

    def __init__(self):
        self.functions = {
            '$if1': 3,  # explicit condition: $if1(cond, then, else)
            '$if2': 2,  # null-coalescing:    $if2(x, fallback)   — returns x if non-empty
            '$if3': 0,  # first non-empty:    $if3(a, b, c, …)    — variable args
            '$ifequal': 4,
            '$ifgreater': 4,
            '$inarray': 3,
            '$lower': 2,
            '$num': 2,
            '$upper': 2,
            '$strchr': 2,
            '$strcmp': 2,
            '$stricmp': 2,
            '$substr': 3,
        }

    def if1(self, cond, string1, string2=''):
        """Explicit conditional: return string1 if cond is truthy, else string2."""
        return str(string1) if cond else str(string2)

    def if2(self, x, fallback=''):
        """Null-coalescing: return x if x is non-empty/non-None, else fallback.

        Unlike $if1, $if2 uses the value itself as the condition, so you only
        need to write it once:
            $if2('%catno%','no-cat')
        is equivalent to:
            $if1($strcmp('%catno%',''),'%catno%','no-cat')
        """
        val = str(x) if x is not None else ''
        return val if val and val != 'None' else str(fallback)

    def if3(self, *args):
        """Return the first non-empty, non-None value from the argument list.

        Useful as a priority chain of fallbacks:
            $if3('%albumartist%','%artist%','Unknown')
        """
        for arg in args:
            val = str(arg) if arg is not None else ''
            if val and val != 'None':
                return val
        return ''

    def ifequal(self, int1, int2, oui, non):
        int1 = 0 if int1 is None or int1 == '' else int(int1)
        int2 = 0 if int2 is None or int2 == '' else int(int2)
        result = oui if int1 == int2 else non
        return result

    def ifgreater(self, int1, int2, oui, non):
        # for convenience if int1 or int2 are None make 0
        int1 = 0 if int1 is None or int1 == '' else int(int1)
        int2 = 0 if int2 is None or int2 == '' else int(int2)
        result = oui if int1 > int2 else non
        return result

    def inarray(self, l, i):
        ''' Returns True or False if item is in array. List passed in as
            an escaped string, so needs parsing
        '''
        itm = '' if i == 'None' else str(i)
        l = re.sub(r'\\', '', l)
        lst = eval(l)
        result = itm in lst

        return result

    def lower(self, string):
        ''' Make string lowercase
        '''
        return str(string).lower()

    def num(self, num, places):
        string = '{:0>%%}'
        string = re.sub(r'\%\%', str(places), string)
        string = string.format(str(num))
        return string

    def strchr(self, string, char):
        "Returns position of first occurrence of character char(s) in string str."
        string = '' if string == 'None' else str(string)
        char = '' if char == 'None' else str(char)
        return string.find(char)

    def strcmp(self, string1, string2):
        string1 = '' if string1 == 'None' else str(string1)
        string2 = '' if string2 == 'None' else str(string2)
        result = string1 == string2
        return result

    def stricmp(self, string1, string2):
        string1 = '' if string1 == 'None' else str(string1)
        string2 = '' if string2 == 'None' else str(string2)
        result = string1.lower() == string2.lower()
        return result

    def substr(self, string, start, finish):
        string = '' if string is None else string
        start = None if start == '' else int(start)
        finish = None if finish == '' else int(finish)
        s = string[start:finish]
        return s

    def upper(self, string):
        ''' Make string uppercase
        '''
        return str(string).upper()

    def parseString(self, string):
        """ Walk through the input string, collecting functions along the way.

            string = 'some text $functionname(arg1,arg2, ...)'

            There is probably a clever way to do this with regex, but doing
            it this way to properly manage nested functions
        """
        output = ''

        # print('parseString, input: {}'.format(string))

        command = ''
        """hierarchy used to track & collect nested functions
        """
        hierarchy = 0
        lastchar = ''
        for c in string:
            if c == '$':
                hierarchy = hierarchy + 1
                command += c
            elif c == '(' and lastchar != '\\':
                if hierarchy > 0:
                    command += c
                else:
                    output += c
            elif c == ')' and lastchar != '\\':
                if hierarchy > 0:
                    hierarchy = hierarchy - 1
                    command += c
                    if hierarchy == 0:
                        result = self.execute(command)
                        output += result
                        command = ''
                else:
                    output += c
            elif hierarchy > 0:
                command += c
            else:
                output += c
            lastchar = c

        # print('parseString, output: {}'.format(output))

        return output

    def execute(self, string):
        """ Unpick the command, validate the function name and arguments
            Returns a string
        """
        output = ''

#TODO:  regex to capture empty & unquoted parameters

        functNameMatch = re.findall(r'(\$[a-z0-9_]+)\(', string)
        for match in functNameMatch:
            if match not in self.functions:
                 return 'unknown command'
        string = re.sub(r'\$', 'self.', string)
        # \( and \) are not valid Python escape sequences (warn in 3.12,
        # error in 3.13).  get_clean_filename strips the backslash anyway,
        # so converting them to bare parens produces identical output.
        string = string.replace('\\(', '(').replace('\\)', ')')
        result = eval(string)

        return result

    def test(self):
        track = {

            'formatted_string': "%albumartist%/[%year%] %album%$if1($strcmp('%totaldiscs%',''),'',$ifgreater('%totaldiscs%', 1,'/CD %discnumber%',''))$if1($strcmp('%disctitle%',''),'',', %disctitle%')/$num('%track%','2') $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ')%title%%fileext%",
            'test': 'Advance/[2014] Deus Ex Machina/09 When we return.flac',
            '%artist%': 'Advance',
            '%albumartist%': 'Advance',
            '%year%': '2014',
            '%album%': 'Deus Ex Machina',
            '%title%': 'When we return',
            '%track%': '9',
            '%fileext%': '.flac',
        }

        multidisctrack = {
            'formatted_string': "%albumartist%/[%year%] %album%$if1($strcmp('%totaldiscs%',''),'',$ifgreater('%totaldiscs%', 1,'/CD %discnumber%',''))$if1($strcmp('%disctitle%',''),'',', %disctitle%')/$num('%track%','2') $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ')%title%%fileext%",
            'test': 'Advance/[2014] Deus Ex Machina/CD 2, Bonus tracks/09 When we return.flac',
            '%artist%': 'Advance',
            '%albumartist%': 'Advance',
            '%year%': '2014',
            '%album%': 'Deus Ex Machina',
            '%discnumber%': '2',
            '%totaldiscs%': '2',
            '%disctitle%': 'Bonus tracks',
            '%title%': 'When we return',
            '%track%': '9',
            '%fileext%': '.flac',
        }

        various = {
            'formatted_string': r"%albumartist%/[%year%] %album% \(%catnumber%\)$if1($strcmp('%totaldiscs%',''),'',$ifgreater('%totaldiscs%', 1,'/CD %discnumber%',''))$if1($strcmp('%disctitle%',''),'',', %disctitle%')/$num('%track%','2') $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ')%title%%fileext%",
            'test': 'Various Artists/[2016] Modern EBM/05 Advance - Dead technology.flac',
            '%artist%': 'Advance',
            '%albumartist%': 'Various Artists',
            '%year%': '2016',
            '%album%': 'Modern EBM',
            '%title%': 'Dead technology',
            '%track%': '5',
            '%fileext%': '.flac',
        }

        passMessage = 'Pass'
        failMessage = 'Fail'

        """Test 1: directly calling function"""
        result = self.num(8,4)
        test = '0008'
        output = 'Output should read: "{}": {}'.format(test, failMessage if result != test else passMessage)
        print(output)

        """Test 2: track from a single artist album"""
        result = stringFormatting.parseString(track['formatted_string'], track)
        output = 'Output should read "{}": {}'.format(track['test'], failMessage if result != track['test'] else passMessage)
        print(output)

        """Test 3: track from a various artist album"""
        result = stringFormatting.parseString(various['formatted_string'], various)
        output = 'Output should read "{}": {}'.format(various['test'], failMessage if result != various['test'] else passMessage)
        print(output)

        """Test 4: track from a multidisc album"""
        result = stringFormatting.parseString(multidisctrack['formatted_string'], multidisctrack)
        output = 'Output should read "{}": {}'.format(multidisctrack['test'], failMessage if result != multidisctrack['test'] else passMessage)
        print(output)

# stringFormatting = StringFormatting()
# stringFormatting.test()
