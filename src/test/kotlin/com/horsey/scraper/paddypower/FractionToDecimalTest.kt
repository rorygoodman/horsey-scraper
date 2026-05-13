package com.horsey.scraper.paddypower

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class FractionToDecimalTest {
    @Test fun `simple fraction 5_2 is 3_5`()  = assertEquals(3.5, fractionalToDecimal("5/2"))
    @Test fun `9_2 is 5_5`()                   = assertEquals(5.5, fractionalToDecimal("9/2"))
    @Test fun `11_4 is 3_75`()                 = assertEquals(3.75, fractionalToDecimal("11/4"))
    @Test fun `1_1 is 2_0`()                   = assertEquals(2.0, fractionalToDecimal("1/1"))
    @Test fun `1_100 is 1_01`()                = assertEquals(1.01, fractionalToDecimal("1/100"))

    @Test fun `evens word form lowercase`()    = assertEquals(2.0, fractionalToDecimal("evens"))
    @Test fun `EVS abbreviation uppercase`()   = assertEquals(2.0, fractionalToDecimal("EVS"))
    @Test fun `Evens mixed case`()             = assertEquals(2.0, fractionalToDecimal("Evens"))
    @Test fun `whitespace-padded fraction`()   = assertEquals(3.5, fractionalToDecimal(" 5/2 "))

    @Test fun `SP returns null`()              = assertNull(fractionalToDecimal("SP"))
    @Test fun `empty string returns null`()    = assertNull(fractionalToDecimal(""))
    @Test fun `garbage returns null`()         = assertNull(fractionalToDecimal("abc"))
    @Test fun `bare slash returns null`()      = assertNull(fractionalToDecimal("/"))
    @Test fun `divide by zero returns null`()  = assertNull(fractionalToDecimal("5/0"))
    @Test fun `negative numerator returns null`() = assertNull(fractionalToDecimal("-1/2"))
    @Test fun `non-integer fraction returns null`() = assertNull(fractionalToDecimal("1.5/2"))
    @Test fun `100_1 is 101_0`()               = assertEquals(101.0, fractionalToDecimal("100/1"))
}
