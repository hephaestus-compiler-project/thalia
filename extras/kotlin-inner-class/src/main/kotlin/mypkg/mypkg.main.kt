package mypkg

class Bar<T> {
    public constructor(x: T) {}
    public inner class Nested<T, Y> {
        public fun m(x: T, y: T): Y = TODO()
        
    }
}
