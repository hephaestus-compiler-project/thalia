package mypkg;

public class Bar<T> {
    public Bar(T x) {}

    public class Nested<T, Y> {
        public Nested m1() { return new Nested(); }

        public Y m(T x, Y y) {
            return null;
        }
    }
}
